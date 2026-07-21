"""Governance interface. v0 ships allow-all, but the interface is load-bearing:
the orchestrator consults the policy before EVERY source fetch, including
relationship expansions, so a real policy (residency, purpose limitation,
consent) drops in without orchestrator changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class FetchRequest(BaseModel):
    source: str
    entity_type: str
    criteria: dict[str, Any] = Field(default_factory=dict)
    purpose: str = "resolution"  # or "relationship_expansion"


class PolicyDecision(BaseModel):
    allowed: bool
    reason: str


class GovernancePolicy(ABC):
    @abstractmethod
    def check(self, request: FetchRequest) -> PolicyDecision: ...


class AllowAllPolicy(GovernancePolicy):
    def check(self, request: FetchRequest) -> PolicyDecision:
        return PolicyDecision(allowed=True, reason="v0 allow-all policy")
