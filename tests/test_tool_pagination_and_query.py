from incident_commander_env import IncidentCommanderEnv


def test_tool_pagination_and_query() -> None:
    env = IncidentCommanderEnv()
    env.reset(seed=123)

    env.step({"type": "list_services", "args": {}})
    env.step(
        {
            "type": "get_metrics",
            "args": {
                "service": "checkout-service",
                "metric": "error_rate",
                "window_steps": 1,
                "agg": "raw",
            },
        }
    )

    _, _, _, broad_info = env.step(
        {
            "type": "get_logs",
            "args": {
                "service": "checkout-service",
                "query": "",
                "window_steps": 3,
                "limit": 5,
                "page": 0,
            },
        }
    )
    broad_lines = broad_info["tool_result"]["lines"]
    assert all("PRICING_URL invalid" not in line["message"] for line in broad_lines)

    _, _, _, paged_info = env.step(
        {
            "type": "get_logs",
            "args": {
                "service": "checkout-service",
                "query": "",
                "window_steps": 4,
                "limit": 5,
                "page": 1,
            },
        }
    )
    assert any(
        "PRICING_URL invalid" in line["message"] for line in paged_info["tool_result"]["lines"]
    )

    _, _, _, specific_info = env.step(
        {
            "type": "get_logs",
            "args": {
                "service": "checkout-service",
                "query": "pricing_url",
                "window_steps": 5,
                "limit": 5,
                "page": 0,
            },
        }
    )
    assert any(
        "PRICING_URL invalid" in line["message"] for line in specific_info["tool_result"]["lines"]
    )
