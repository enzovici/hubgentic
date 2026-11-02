"""Per-tenant catalog runtime.

Each tenant gets its own FederationOrchestrator so the explanation cache
(request_id -> lineage) is never shared across tenants, and its own governance
policy so a workspace admin can switch source systems off for that workspace
only. The policy reads the tenant's settings on every fetch, so toggles apply
to the next query without rebuilding anything.
"""
from __future__ import annotations

import threading

from hubgentic.app import build_orchestrator
from hubgentic.federation.orchestrator import FederationOrchestrator
from hubgentic.governance.policy import FetchRequest, GovernancePolicy, PolicyDecision
from hubgentic.web.db import Database


class TenantSourcePolicy(GovernancePolicy):
    def __init__(self, db: Database, tenant_id: int) -> None:
        self._db = db
        self._tenant_id = tenant_id

    def check(self, request: FetchRequest) -> PolicyDecision:
        if request.source in self._db.disabled_sources(self._tenant_id):
            return PolicyDecision(
                allowed=False, reason="disabled by workspace governance settings"
            )
        return PolicyDecision(allowed=True, reason="enabled for this workspace")


class TenantRuntimes:
    def __init__(self, db: Database, **adapter_kwargs) -> None:
        self._db = db
        self._adapter_kwargs = adapter_kwargs
        self._runtimes: dict[int, FederationOrchestrator] = {}
        self._lock = threading.Lock()

    def get(self, tenant_id: int) -> FederationOrchestrator:
        with self._lock:
            orch = self._runtimes.get(tenant_id)
            if orch is None:
                orch = build_orchestrator(
                    policy=TenantSourcePolicy(self._db, tenant_id),
                    **self._adapter_kwargs,
                )
                self._runtimes[tenant_id] = orch
            return orch
