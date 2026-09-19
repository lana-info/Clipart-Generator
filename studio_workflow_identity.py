"""Core-owned module identities and reusable legacy state scopes, not entitlements."""
from types import MappingProxyType


LEGACY_WORKFLOW_IDS = frozenset({"clipart", "processing", "pinterest"})
AUTO_CLIPART_MODULE_ID = "auto-clipart"
_STATE_SCOPES = MappingProxyType({
    **{module_id: module_id for module_id in LEGACY_WORKFLOW_IDS},
    AUTO_CLIPART_MODULE_ID: "clipart",
})


def workflow_state_scope(module_id: str) -> str:
    try:
        return _STATE_SCOPES[module_id]
    except (KeyError, TypeError) as exc:
        raise ValueError("Workflow module scope is invalid") from exc
