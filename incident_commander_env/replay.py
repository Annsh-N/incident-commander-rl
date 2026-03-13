"""Replay buffer utilities."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any


def hash_observation(observation: dict[str, Any]) -> str:
    """Create a deterministic hash for an observation."""

    payload = json.dumps(observation, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class ReplayEntry:
    """Single replay event."""

    step: int
    obs: dict[str, Any]
    obs_hash: str
    action: dict[str, Any]
    reward: float
    done: bool
    info: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReplayBuffer:
    """In-memory replay buffer for later persistence."""

    entries: list[ReplayEntry]

    def append(
        self,
        step: int,
        observation: dict[str, Any],
        action: dict[str, Any],
        reward: float,
        done: bool,
        info: dict[str, Any],
    ) -> None:
        self.entries.append(
            ReplayEntry(
                step=step,
                obs=deepcopy(observation),
                obs_hash=hash_observation(observation),
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
