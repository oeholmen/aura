from __future__ import annotations

from typing import Any, Dict, Optional

from core.health.degraded_events import get_unified_failure_state
from core.runtime.service_access import (
    resolve_canonical_self,
    resolve_identity_model,
    resolve_orchestrator,
    resolve_state_repository,
)


def _canonical_self_version(current: Any) -> Optional[int]:
    try:
        return int(getattr(current, "version", 0) or 0)
    except (TypeError, ValueError):
        return None


def get_organism_status(orchestrator: Any = None) -> Dict[str, Any]:
    orch = orchestrator or resolve_orchestrator(default=None)
    repo = resolve_state_repository(orch, default=None)
    state = getattr(repo, "_current", None) if repo is not None else None
    cognition = getattr(state, "cognition", None) if state is not None else None

    canonical_self = resolve_canonical_self(default=None)
    canonical_self_version = _canonical_self_version(canonical_self)
    identity_model = resolve_identity_model(default=None)
    failure_state = get_unified_failure_state(limit=25)

    current_intention = ""
    if canonical_self is not None:
        current_intention = str(getattr(canonical_self, "current_intention", "") or "")
    identity_name = ""
    if canonical_self is not None:
        identity_name = str(getattr(getattr(canonical_self, "identity", None), "name", "") or "")
    if not identity_name and identity_model is not None:
        identity_name = str(
            getattr(identity_model, "name", "")
            or getattr(getattr(identity_model, "state", None), "self_narrative", "")
            or ""
        )
    if not identity_name:
        identity_name = "Aura"

    return {
        "identity_surface": "canonical_self" if canonical_self is not None else "fallback_identity",
        "identity_name": identity_name,
        "canonical_self_version": canonical_self_version,
        "state_version": getattr(state, "version", None) if state is not None else None,
        "failure_state": failure_state,
        "failure_pressure": float(failure_state.get("pressure", 0.0) or 0.0),
        "current_objective": str(getattr(cognition, "current_objective", "") or "") if cognition is not None else "",
        "current_intention": current_intention,
        "pending_initiatives": len(list(getattr(cognition, "pending_initiatives", []) or [])) if cognition is not None else 0,
        "active_goals": len(list(getattr(cognition, "active_goals", []) or [])) if cognition is not None else 0,
    }
