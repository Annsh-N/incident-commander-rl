"""Replay buffer utilities with JSONL persistence."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


def hash_observation(observation: dict[str, Any]) -> str:
    """Create a deterministic hash for an observation."""

    payload = json.dumps(observation, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def deterministic_episode_id(scenario_id: str, seed: int | None) -> str:
    """Create a deterministic episode identifier."""

    payload = f"{scenario_id}::{seed}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def compact_observation(observation: dict[str, Any]) -> dict[str, Any]:
    """Store a compact observation subset for replay logs."""

    return {
        "hash": hash_observation(observation),
        "step": observation["step"],
        "status": observation["status"],
        "alert_ids": [alert["id"] for alert in observation["alerts"]],
        "metrics_snapshot": deepcopy(observation["metrics_snapshot"]),
        "evidence_flags": deepcopy(observation["evidence_flags"]),
        "incident_created": observation["incident"]["created"],
    }


@dataclass
class ReplayEntry:
    """Single replay event."""

    episode_id: str
    scenario_id: str
    seed: int | None
    t: int
    obs: dict[str, Any]
    action: dict[str, Any]
    reward: float
    done: bool
    info: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReplayBuffer:
    """In-memory replay buffer with disk persistence."""

    entries: list[ReplayEntry]
    episode_id: str | None = None
    scenario_id: str | None = None
    seed: int | None = None

    def set_context(self, scenario_id: str, seed: int | None) -> None:
        self.scenario_id = scenario_id
        self.seed = seed
        self.episode_id = deterministic_episode_id(scenario_id, seed)

    def append(
        self,
        step: int,
        observation: dict[str, Any],
        action: dict[str, Any],
        reward: float,
        done: bool,
        info: dict[str, Any],
    ) -> None:
        if self.episode_id is None or self.scenario_id is None:
            raise RuntimeError("ReplayBuffer context must be set before appending")
        self.entries.append(
            ReplayEntry(
                episode_id=self.episode_id,
                scenario_id=self.scenario_id,
                seed=self.seed,
                t=step,
                obs=compact_observation(observation),
                action=deepcopy(action),
                reward=reward,
                done=done,
                info=deepcopy(info),
            )
        )

    def reset(self) -> None:
        self.entries.clear()

    def as_list(self) -> list[dict[str, Any]]:
        return [entry.to_dict() for entry in self.entries]

    def save_replay(self, path: str) -> None:
        save_replay(self.as_list(), path)


def save_replay(events: list[dict[str, Any]], path: str) -> None:
    """Save replay events to JSONL deterministically."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


def load_replay(path: str) -> list[dict[str, Any]]:
    """Load replay events from JSONL."""

    target = Path(path)
    with target.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def replay_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize a replay."""

    total_reward = round(sum(float(event["reward"]) for event in events), 10)
    final_event = events[-1] if events else {}
    failure_histogram: dict[str, int] = {}
    for event in events:
        for reason in event.get("info", {}).get("failure_reasons", []):
            failure_histogram[reason] = failure_histogram.get(reason, 0) + 1
    return {
        "episode_id": final_event.get("episode_id"),
        "scenario_id": final_event.get("scenario_id"),
        "seed": final_event.get("seed"),
        "steps": len(events),
        "total_reward": total_reward,
        "resolution": final_event.get("info", {}).get("resolution"),
        "failure_reasons": failure_histogram,
    }
