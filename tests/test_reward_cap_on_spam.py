from incident_commander_env import IncidentCommanderEnv


def test_reward_cap_on_spam() -> None:
    env = IncidentCommanderEnv()
    env.reset(seed=123)

    rewards: list[float] = []
    infos: list[dict] = []
    action = {
        "type": "get_metrics",
        "args": {
            "service": "checkout-service",
            "metric": "error_rate",
            "window_steps": 1,
            "agg": "raw",
        },
    }

    for _ in range(5):
        _, reward, _, info = env.step(action)
        rewards.append(reward)
        infos.append(info)

    assert sum(rewards) < 0.0
    assert any("spam penalty" in " ".join(info["debug"]) for info in infos[-2:])
