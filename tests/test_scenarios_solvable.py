from incident_commander_env import IncidentCommanderEnv
from incident_commander_env.scenario import load_base_scenarios


BASE_SCRIPTS = {
    "deploy-regression-config-bug": [
        {"type": "create_incident", "args": {"title": "Deploy regression", "severity": "sev1"}},
        {"type": "get_metrics", "args": {"service": "checkout-service", "metric": "error_rate", "window_steps": 1, "agg": "raw"}},
        {"type": "get_logs", "args": {"service": "checkout-service", "query": "PRICING_URL", "window_steps": 5, "limit": 10, "page": 0}},
        {"type": "diff_config", "args": {"service": "checkout-service", "from_version": "v41", "to_version": "v42"}},
        {"type": "post_update", "args": {"audience": "internal", "template_id": "status", "fields": {"summary": "Config regression identified", "eta": "10 minutes"}}},
        {"type": "apply_mitigation", "args": {"mitigation_id": "rollback_checkout_v42_to_v41"}},
        {"type": "rollback_deploy", "args": {"service": "checkout-service", "from_version": "v42", "to_version": "v41"}},
        {"type": "wait", "args": {"steps": 1}},
        {"type": "confirm_metrics_normalized", "args": {"service": "checkout-service", "metric": "error_rate", "target": 2.5, "window_steps": 1}},
        {"type": "confirm_metrics_normalized", "args": {"service": "checkout-service", "metric": "p95_latency", "target": 700.0, "window_steps": 1}},
        {"type": "post_update", "args": {"audience": "internal", "template_id": "resolved", "fields": {"summary": "Rollback complete", "customer_impact": "Recovered"}}},
        {"type": "declare_resolved", "args": {"root_cause_id": "checkout_pricing_url_misconfigured_after_v42_deploy", "mitigation_id": "rollback_checkout_v42_to_v41", "summary": "Resolved by rollback"}}
    ],
    "database-connection-exhaustion": [
        {"type": "create_incident", "args": {"title": "DB pool exhaustion", "severity": "sev1"}},
        {"type": "get_logs", "args": {"service": "checkout-service", "query": "connections", "window_steps": 5, "limit": 10, "page": 0}},
        {"type": "diff_config", "args": {"service": "checkout-service", "from_version": "v32", "to_version": "v33"}},
        {"type": "post_update", "args": {"audience": "internal", "template_id": "status", "fields": {"summary": "Pool limit regression found", "eta": "15 minutes"}}},
        {"type": "apply_mitigation", "args": {"mitigation_id": "increase_db_pool_limit_and_scale_checkout"}},
        {"type": "apply_config_patch", "args": {"service": "checkout-service", "patch_id": "raise_db_pool_limit"}},
        {"type": "scale_service", "args": {"service": "checkout-service", "replicas": 12}},
        {"type": "wait", "args": {"steps": 1}},
        {"type": "confirm_metrics_normalized", "args": {"service": "checkout-service", "metric": "error_rate", "target": 2.5, "window_steps": 1}},
        {"type": "confirm_metrics_normalized", "args": {"service": "orders-db", "metric": "db_conn", "target": 80.0, "window_steps": 1}},
        {"type": "post_update", "args": {"audience": "internal", "template_id": "resolved", "fields": {"summary": "Pool and scale fix applied", "customer_impact": "Recovered"}}},
        {"type": "declare_resolved", "args": {"root_cause_id": "checkout_pool_limit_too_low_under_burst_traffic", "mitigation_id": "increase_db_pool_limit_and_scale_checkout", "summary": "Resolved with pool increase and scale out"}}
    ],
    "queue-backlog-downstream-timeouts": [
        {"type": "create_incident", "args": {"title": "Queue backlog", "severity": "sev1"}},
        {"type": "get_logs", "args": {"service": "fulfillment-worker", "query": "consumer", "window_steps": 5, "limit": 10, "page": 0}},
        {"type": "diff_config", "args": {"service": "fulfillment-worker", "from_version": "v14", "to_version": "v15"}},
        {"type": "post_update", "args": {"audience": "internal", "template_id": "status", "fields": {"summary": "Worker concurrency too low", "eta": "10 minutes"}}},
        {"type": "apply_mitigation", "args": {"mitigation_id": "increase_consumer_concurrency"}},
        {"type": "apply_config_patch", "args": {"service": "fulfillment-worker", "patch_id": "increase_consumer_concurrency"}},
        {"type": "wait", "args": {"steps": 3}},
        {"type": "confirm_metrics_normalized", "args": {"service": "fulfillment-worker", "metric": "queue_depth", "target": 20.0, "window_steps": 1}},
        {"type": "confirm_metrics_normalized", "args": {"service": "checkout-api", "metric": "p95_latency", "target": 700.0, "window_steps": 1}},
        {"type": "post_update", "args": {"audience": "internal", "template_id": "resolved", "fields": {"summary": "Worker backlog drained", "customer_impact": "Recovered"}}},
        {"type": "declare_resolved", "args": {"root_cause_id": "worker_concurrency_too_low_for_order_queue", "mitigation_id": "increase_consumer_concurrency", "summary": "Raised worker concurrency and recovered"}}
    ],
    "partial-dependency-outage": [
        {"type": "create_incident", "args": {"title": "Catalog fallback", "severity": "sev2"}},
        {"type": "get_logs", "args": {"service": "api-gateway", "query": "503", "window_steps": 5, "limit": 10, "page": 0}},
        {"type": "get_trace_sample", "args": {"service": "api-gateway", "trace_id": "trace-catalog-001"}},
        {"type": "post_update", "args": {"audience": "internal", "template_id": "status", "fields": {"summary": "Dependency 503s confirmed", "eta": "10 minutes"}}},
        {"type": "apply_mitigation", "args": {"mitigation_id": "enable_catalog_fallback"}},
        {"type": "toggle_feature_flag", "args": {"flag": "catalog_fallback_enabled", "enabled": True}},
        {"type": "wait", "args": {"steps": 1}},
        {"type": "confirm_metrics_normalized", "args": {"service": "api-gateway", "metric": "error_rate", "target": 2.5, "window_steps": 1}},
        {"type": "confirm_metrics_normalized", "args": {"service": "catalog-service", "metric": "dependency_503_rate", "target": 5.0, "window_steps": 1}},
        {"type": "post_update", "args": {"audience": "internal", "template_id": "resolved", "fields": {"summary": "Fallback enabled", "customer_impact": "Recovered"}}},
        {"type": "declare_resolved", "args": {"root_cause_id": "catalog_dependency_partial_outage_needs_fallback", "mitigation_id": "enable_catalog_fallback", "summary": "Enabled fallback and stabilized"}}
    ],
    "memory-leak-after-deploy": [
        {"type": "create_incident", "args": {"title": "Memory leak", "severity": "sev1"}},
        {"type": "search_recent_deploys", "args": {"service": "checkout-api", "window_steps": 5}},
        {"type": "get_logs", "args": {"service": "checkout-api", "query": "OOM", "window_steps": 5, "limit": 10, "page": 0}},
        {"type": "post_update", "args": {"audience": "internal", "template_id": "status", "fields": {"summary": "Leaking deploy identified", "eta": "10 minutes"}}},
        {"type": "apply_mitigation", "args": {"mitigation_id": "rollback_checkout_v52_to_v51"}},
        {"type": "rollback_deploy", "args": {"service": "checkout-api", "from_version": "v52", "to_version": "v51"}},
        {"type": "wait", "args": {"steps": 1}},
        {"type": "confirm_metrics_normalized", "args": {"service": "checkout-api", "metric": "memory_usage", "target": 70.0, "window_steps": 1}},
        {"type": "confirm_metrics_normalized", "args": {"service": "checkout-api", "metric": "error_rate", "target": 2.5, "window_steps": 1}},
        {"type": "post_update", "args": {"audience": "internal", "template_id": "resolved", "fields": {"summary": "Rollback stopped the leak", "customer_impact": "Recovered"}}},
        {"type": "declare_resolved", "args": {"root_cause_id": "checkout_memory_leak_after_v52_deploy", "mitigation_id": "rollback_checkout_v52_to_v51", "summary": "Rolled back leaking release"}}
    ],
    "bad-dns-networking-config": [
        {"type": "create_incident", "args": {"title": "DNS config issue", "severity": "sev1"}},
        {"type": "get_logs", "args": {"service": "checkout-api", "query": "resolve", "window_steps": 5, "limit": 10, "page": 0}},
        {"type": "get_trace_sample", "args": {"service": "checkout-api", "trace_id": "trace-dns-001"}},
        {"type": "post_update", "args": {"audience": "internal", "template_id": "status", "fields": {"summary": "Resolver issue confirmed", "eta": "10 minutes"}}},
        {"type": "apply_mitigation", "args": {"mitigation_id": "revert_dns_resolver_list"}},
        {"type": "apply_config_patch", "args": {"service": "checkout-api", "patch_id": "revert_dns_resolver_list"}},
        {"type": "wait", "args": {"steps": 1}},
        {"type": "confirm_metrics_normalized", "args": {"service": "checkout-api", "metric": "error_rate", "target": 2.5, "window_steps": 1}},
        {"type": "confirm_metrics_normalized", "args": {"service": "checkout-api", "metric": "p95_latency", "target": 700.0, "window_steps": 1}},
        {"type": "post_update", "args": {"audience": "internal", "template_id": "resolved", "fields": {"summary": "Resolver config reverted", "customer_impact": "Recovered"}}},
        {"type": "declare_resolved", "args": {"root_cause_id": "dns_resolver_config_broken_for_tax_service", "mitigation_id": "revert_dns_resolver_list", "summary": "Reverted DNS resolver list"}}
    ],
    "retry-storm-thundering-herd": [
        {"type": "create_incident", "args": {"title": "Retry storm", "severity": "sev1"}},
        {"type": "get_logs", "args": {"service": "api-gateway", "query": "retry", "window_steps": 5, "limit": 10, "page": 0}},
        {"type": "diff_config", "args": {"service": "api-gateway", "from_version": "v44", "to_version": "v45"}},
        {"type": "post_update", "args": {"audience": "internal", "template_id": "status", "fields": {"summary": "Retry storm identified", "eta": "10 minutes"}}},
        {"type": "post_update", "args": {"audience": "external", "template_id": "status", "fields": {"summary": "Mitigation underway", "eta": "10 minutes"}}},
        {"type": "apply_mitigation", "args": {"mitigation_id": "disable_aggressive_retries"}},
        {"type": "toggle_feature_flag", "args": {"flag": "aggressive_retries", "enabled": False}},
        {"type": "wait", "args": {"steps": 1}},
        {"type": "confirm_metrics_normalized", "args": {"service": "api-gateway", "metric": "retry_rate", "target": 15.0, "window_steps": 1}},
        {"type": "confirm_metrics_normalized", "args": {"service": "api-gateway", "metric": "p95_latency", "target": 700.0, "window_steps": 1}},
        {"type": "post_update", "args": {"audience": "internal", "template_id": "resolved", "fields": {"summary": "Retry storm stopped", "customer_impact": "Recovered"}}},
        {"type": "declare_resolved", "args": {"root_cause_id": "aggressive_retry_policy_created_thundering_herd", "mitigation_id": "disable_aggressive_retries", "summary": "Disabled aggressive retries"}}
    ],
    "security-permission-denied": [
        {"type": "create_incident", "args": {"title": "Permission denied", "severity": "sev1"}},
        {"type": "view_runbook", "args": {"service": "iam-proxy", "section": "triage"}},
        {"type": "get_logs", "args": {"service": "checkout-api", "query": "AccessDenied", "window_steps": 5, "limit": 10, "page": 0}},
        {"type": "diff_config", "args": {"service": "iam-proxy", "from_version": "checkout-policy-v18", "to_version": "checkout-policy-v19"}},
        {"type": "post_update", "args": {"audience": "internal", "template_id": "status", "fields": {"summary": "IAM rollback required", "eta": "10 minutes"}}},
        {"type": "apply_mitigation", "args": {"mitigation_id": "rollback_receipt_permission"}},
        {"type": "apply_config_patch", "args": {"service": "iam-proxy", "patch_id": "rollback_receipt_permission"}},
        {"type": "wait", "args": {"steps": 1}},
        {"type": "confirm_metrics_normalized", "args": {"service": "checkout-api", "metric": "access_denied_rate", "target": 5.0, "window_steps": 1}},
        {"type": "confirm_metrics_normalized", "args": {"service": "checkout-api", "metric": "error_rate", "target": 2.5, "window_steps": 1}},
        {"type": "post_update", "args": {"audience": "internal", "template_id": "resolved", "fields": {"summary": "IAM permission restored", "customer_impact": "Recovered"}}},
        {"type": "declare_resolved", "args": {"root_cause_id": "checkout_iam_policy_removed_receipt_permission", "mitigation_id": "rollback_receipt_permission", "summary": "Rolled back bad IAM policy"}}
    ]
}


def test_scenarios_solvable() -> None:
    for scenario in load_base_scenarios():
        env = IncidentCommanderEnv(scenario=scenario)
        env.reset(seed=123)
        info = {}
        done = False

        for action in BASE_SCRIPTS[scenario.id]:
            _, _, done, info = env.step(action)
            if done:
                break

        assert done is True, scenario.id
        assert info["resolution"] == "success", scenario.id
