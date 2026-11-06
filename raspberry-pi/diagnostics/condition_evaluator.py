"""Configurable, transparent per-metric and overall condition evaluation."""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from processing.vibration import VibrationFeatures
from sensors.models import SensorSnapshot


class ConditionStatus(str, Enum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    OFFLINE = "OFFLINE"
    UNCONFIGURED = "UNCONFIGURED"
    MISSING = "MISSING"


STATUS_CODES = {
    ConditionStatus.UNCONFIGURED: -1,
    ConditionStatus.MISSING: -2,
    ConditionStatus.NORMAL: 0,
    ConditionStatus.WARNING: 1,
    ConditionStatus.CRITICAL: 2,
    ConditionStatus.OFFLINE: 3,
}


@dataclass(frozen=True)
class MetricCondition:
    name: str
    value: Optional[float]
    status: ConditionStatus
    evidence: str

    @property
    def code(self) -> int:
        return STATUS_CODES[self.status]


@dataclass(frozen=True)
class EvaluationResult:
    status: ConditionStatus
    metrics: Dict[str, MetricCondition]
    evidence: List[str]
    telemetry_age_seconds: float


class ConditionEvaluator:
    def __init__(self, thresholds: Dict[str, Any]) -> None:
        self._thresholds = thresholds

    @staticmethod
    def _configured(config: Dict[str, Any]) -> bool:
        return any(value is not None for value in config.values())

    def _evaluate_metric(
        self,
        name: str,
        value: Optional[float],
        config: Dict[str, Any],
        evaluate_normal_low: bool = True,
    ) -> MetricCondition:
        if value is None:
            return MetricCondition(name, value, ConditionStatus.MISSING, "{} unavailable".format(name))
        if not self._configured(config):
            return MetricCondition(
                name,
                value,
                ConditionStatus.UNCONFIGURED,
                "{} threshold not configured".format(name),
            )

        critical_high = config.get("critical_high")
        warning_high = config.get("warning_high")
        critical_low = config.get("critical_low")
        warning_low = config.get("warning_low")
        normal_low = config.get("normal_low") if evaluate_normal_low else None

        if critical_high is not None and value > float(critical_high):
            return MetricCondition(
                name,
                value,
                ConditionStatus.CRITICAL,
                "{} {:.4g} is above critical high {:.4g}".format(
                    name, value, float(critical_high)
                ),
            )
        if critical_low is not None and value < float(critical_low):
            return MetricCondition(
                name,
                value,
                ConditionStatus.CRITICAL,
                "{} {:.4g} is below critical low {:.4g}".format(
                    name, value, float(critical_low)
                ),
            )
        if warning_high is not None and value >= float(warning_high):
            return MetricCondition(
                name,
                value,
                ConditionStatus.WARNING,
                "{} {:.4g} is at/above warning high {:.4g}".format(
                    name, value, float(warning_high)
                ),
            )
        if warning_low is not None and value <= float(warning_low):
            return MetricCondition(
                name,
                value,
                ConditionStatus.WARNING,
                "{} {:.4g} is at/below warning low {:.4g}".format(
                    name, value, float(warning_low)
                ),
            )
        if normal_low is not None and value < float(normal_low):
            return MetricCondition(
                name,
                value,
                ConditionStatus.WARNING,
                "{} {:.4g} is below the running normal band {:.4g}".format(
                    name, value, float(normal_low)
                ),
            )
        return MetricCondition(name, value, ConditionStatus.NORMAL, "{} within configured range".format(name))

    def evaluate(
        self,
        snapshot: SensorSnapshot,
        vibration: Optional[VibrationFeatures],
        now: Optional[datetime] = None,
    ) -> EvaluationResult:
        current_time = now or datetime.now(timezone.utc)
        age_seconds = max(0.0, (current_time - snapshot.timestamp).total_seconds())
        stale_timeout = float(self._thresholds.get("stale_timeout_seconds", 30))
        if age_seconds > stale_timeout:
            return EvaluationResult(
                status=ConditionStatus.OFFLINE,
                metrics={},
                evidence=[
                    "No recent telemetry received ({:.1f}s > {:.1f}s timeout)".format(
                        age_seconds, stale_timeout
                    )
                ],
                telemetry_age_seconds=age_seconds,
            )

        electrical = snapshot.electrical
        values: Dict[str, Optional[float]] = {
            "temperature_C": snapshot.temperature_c,
            "voltage_V": electrical.voltage_v if electrical else None,
            "current_A": electrical.current_a if electrical else None,
            "power_W": electrical.power_w if electrical else None,
            "vibration_rms_g": vibration.vibration_rms_g if vibration else None,
            "vibration_peak_g": vibration.vibration_peak_g if vibration else None,
            "crest_factor": vibration.crest_factor if vibration else None,
            "kurtosis": vibration.kurtosis if vibration else None,
            "dominant_frequency_Hz": vibration.dominant_frequency_hz if vibration else None,
            "shaft_frequency_Hz": vibration.shaft_frequency_hz if vibration else None,
        }
        metrics: Dict[str, MetricCondition] = {}
        for name, value in values.items():
            evaluate_low = not (
                name == "current_A" and not snapshot.fan_expected_running
            )
            metrics[name] = self._evaluate_metric(
                name,
                value,
                dict(self._thresholds.get(name, {})),
                evaluate_normal_low=evaluate_low,
            )

        ranked = [
            metric.status
            for metric in metrics.values()
            if metric.status in (ConditionStatus.WARNING, ConditionStatus.CRITICAL)
        ]
        if ConditionStatus.CRITICAL in ranked:
            overall = ConditionStatus.CRITICAL
        elif ConditionStatus.WARNING in ranked or snapshot.errors:
            overall = ConditionStatus.WARNING
        else:
            overall = ConditionStatus.NORMAL

        available_groups = sum(
            [
                snapshot.temperature_c is not None,
                snapshot.electrical is not None,
                snapshot.acceleration is not None,
            ]
        )
        if available_groups == 0:
            overall = ConditionStatus.CRITICAL

        evidence = [
            metric.evidence
            for metric in metrics.values()
            if metric.status in (ConditionStatus.WARNING, ConditionStatus.CRITICAL)
        ]
        evidence.extend(
            "{} sensor error: {}".format(name, message)
            for name, message in sorted(snapshot.errors.items())
        )
        if not evidence:
            evidence.append("All configured conditions are within range")

        return EvaluationResult(
            status=overall,
            metrics=metrics,
            evidence=evidence,
            telemetry_age_seconds=age_seconds,
        )
