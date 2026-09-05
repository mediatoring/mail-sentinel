"""Example administrator-installed, read-only tool. No network requests."""
from sentinel.tools import Tool, schema


def register(registry):
    def check_registry_health():
        return {
            "vendor_count": len(registry.org.get("vendors", [])),
            "policy_count": len(registry.org.get("policies", [])),
            "note": "Counts only; this does not verify data freshness."
        }
    registry.add(Tool("registry_health", "Check whether local vendor and policy evidence is configured.", schema(), check_registry_health))
