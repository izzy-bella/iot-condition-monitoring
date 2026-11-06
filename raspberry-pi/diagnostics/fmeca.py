"""Configuration-driven FMECA lookup and RPN validation."""

from dataclasses import dataclass
from typing import Any, Dict, Iterable


@dataclass(frozen=True)
class FMECAAssessment:
    failure_mode: str
    severity: int
    occurrence: int
    detectability: int
    rpn: int
    maintenance_priority: str
    recommended_action: str


class FMECAEvaluator:
    def __init__(self, config: Dict[str, Any]) -> None:
        entries: Iterable[Dict[str, Any]] = config.get("failure_modes", [])
        self._entries = {str(entry["key"]): entry for entry in entries}
        for key, entry in self._entries.items():
            calculated = (
                int(entry["severity"])
                * int(entry["occurrence"])
                * int(entry["detectability"])
            )
            configured = int(entry.get("risk_priority_number", calculated))
            if configured != calculated:
                raise ValueError(
                    "FMECA RPN mismatch for {}: configured {}, calculated {}".format(
                        key, configured, calculated
                    )
                )

    def assess(self, diagnostic_key: str, fallback_action: str) -> FMECAAssessment:
        entry = self._entries.get(diagnostic_key)
        if entry is None:
            return FMECAAssessment(
                failure_mode="Normal operation",
                severity=0,
                occurrence=0,
                detectability=0,
                rpn=0,
                maintenance_priority="ROUTINE",
                recommended_action=fallback_action,
            )
        severity = int(entry["severity"])
        occurrence = int(entry["occurrence"])
        detectability = int(entry["detectability"])
        return FMECAAssessment(
            failure_mode=str(entry["failure_mode"]),
            severity=severity,
            occurrence=occurrence,
            detectability=detectability,
            rpn=severity * occurrence * detectability,
            maintenance_priority=str(entry["maintenance_priority"]),
            recommended_action=str(entry.get("recommended_action", fallback_action)),
        )
