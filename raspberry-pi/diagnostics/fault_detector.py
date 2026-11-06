"""Transparent multi-symptom fault detection and possible-fault diagnosis."""

from dataclasses import dataclass
from typing import List, Optional

from .condition_evaluator import ConditionStatus, EvaluationResult
from processing.vibration import VibrationFeatures
from sensors.models import SensorSnapshot


@dataclass(frozen=True)
class DiagnosticResult:
    key: str
    suspected_fault: str
    evidence: List[str]
    confidence: str
    recommended_action: str


def _abnormal(evaluation: EvaluationResult, name: str) -> bool:
    metric = evaluation.metrics.get(name)
    return bool(
        metric
        and metric.status in (ConditionStatus.WARNING, ConditionStatus.CRITICAL)
    )


class FaultDetector:
    def diagnose(
        self,
        snapshot: SensorSnapshot,
        vibration: Optional[VibrationFeatures],
        evaluation: EvaluationResult,
        vibration_increasing: bool = False,
    ) -> DiagnosticResult:
        if evaluation.status == ConditionStatus.OFFLINE:
            return DiagnosticResult(
                key="communication_failure",
                suspected_fault="Communications / telemetry fault",
                evidence=list(evaluation.evidence),
                confidence="HIGH",
                recommended_action="No recent telemetry received. Check Raspberry Pi, sensors and network connectivity.",
            )

        if snapshot.errors and evaluation.status != ConditionStatus.CRITICAL:
            return DiagnosticResult(
                key="sensor_failure",
                suspected_fault="Sensor fault",
                evidence=list(evaluation.evidence),
                confidence="HIGH",
                recommended_action="Inspect Raspberry Pi sensor wiring, interfaces and sensor health.",
            )

        temperature_high = _abnormal(evaluation, "temperature_C")
        current_high = _abnormal(evaluation, "current_A")
        voltage_abnormal = _abnormal(evaluation, "voltage_V")
        power_high = _abnormal(evaluation, "power_W")
        rms_high = _abnormal(evaluation, "vibration_rms_g")
        peak_high = _abnormal(evaluation, "vibration_peak_g")
        crest_high = _abnormal(evaluation, "crest_factor")
        kurtosis_high = _abnormal(evaluation, "kurtosis")
        frequency_abnormal = _abnormal(
            evaluation, "dominant_frequency_Hz"
        ) or _abnormal(evaluation, "shaft_frequency_Hz")

        if voltage_abnormal:
            return DiagnosticResult(
                "power_supply_abnormality",
                "Power supply abnormality",
                [evaluation.metrics["voltage_V"].evidence],
                "HIGH",
                "Inspect the 12 V supply, wiring and electrical connections.",
            )

        if kurtosis_high and (crest_high or peak_high):
            evidence = [evaluation.metrics["kurtosis"].evidence]
            if crest_high:
                evidence.append(evaluation.metrics["crest_factor"].evidence)
            if peak_high:
                evidence.append(evaluation.metrics["vibration_peak_g"].evidence)
            return DiagnosticResult(
                "bearing_degradation",
                "Possible bearing degradation",
                evidence,
                "HIGH" if len(evidence) > 1 else "MEDIUM",
                "Inspect bearing condition and plan maintenance before further degradation.",
            )

        if crest_high or (peak_high and kurtosis_high):
            evidence = [
                evaluation.metrics[name].evidence
                for name in ("crest_factor", "vibration_peak_g", "kurtosis")
                if _abnormal(evaluation, name)
            ]
            return DiagnosticResult(
                "mechanical_looseness",
                "Suspected mechanical looseness",
                evidence,
                "MEDIUM" if len(evidence) == 1 else "HIGH",
                "Inspect mounting points and tighten loose mechanical connections.",
            )

        if rms_high and (frequency_abnormal or vibration_increasing):
            evidence = [evaluation.metrics["vibration_rms_g"].evidence]
            if frequency_abnormal:
                evidence.extend(
                    evaluation.metrics[name].evidence
                    for name in ("dominant_frequency_Hz", "shaft_frequency_Hz")
                    if _abnormal(evaluation, name)
                )
            if vibration_increasing:
                evidence.append("Vibration RMS increased across the configured trend window")
            return DiagnosticResult(
                "fan_imbalance",
                "Possible fan imbalance",
                evidence,
                "MEDIUM" if len(evidence) == 1 else "HIGH",
                "Inspect fan blades and balance. Check for dirt, damage or uneven loading.",
            )

        if current_high and (rms_high or power_high):
            evidence = [evaluation.metrics["current_A"].evidence]
            if rms_high:
                evidence.append(evaluation.metrics["vibration_rms_g"].evidence)
            if power_high:
                evidence.append(evaluation.metrics["power_W"].evidence)
            return DiagnosticResult(
                "motor_fan_overload",
                "Elevated electrical load",
                evidence,
                "HIGH" if len(evidence) > 1 else "MEDIUM",
                "Inspect fan loading, obstruction and mechanical resistance before continued operation.",
            )

        if temperature_high and current_high:
            return DiagnosticResult(
                "motor_fan_overload",
                "Elevated electrical load with heating",
                [
                    evaluation.metrics["temperature_C"].evidence,
                    evaluation.metrics["current_A"].evidence,
                ],
                "HIGH",
                "Inspect fan loading, obstruction and mechanical resistance before continued operation.",
            )

        if temperature_high and evaluation.metrics["temperature_C"].status == ConditionStatus.CRITICAL:
            return DiagnosticResult(
                "overheating",
                "Overheating",
                [evaluation.metrics["temperature_C"].evidence],
                "MEDIUM",
                "Temperature is elevated. Inspect airflow and thermal condition.",
            )

        if temperature_high:
            return DiagnosticResult(
                "airflow_restriction",
                "Possible airflow restriction",
                [evaluation.metrics["temperature_C"].evidence],
                "LOW",
                "Temperature is elevated. Inspect the airflow path and thermal condition.",
            )

        if current_high:
            return DiagnosticResult(
                "motor_fan_overload",
                "Elevated electrical load",
                [evaluation.metrics["current_A"].evidence],
                "MEDIUM",
                "Current consumption is elevated. Inspect fan loading or mechanical resistance.",
            )

        if rms_high or peak_high or frequency_abnormal:
            evidence = [
                evaluation.metrics[name].evidence
                for name in (
                    "vibration_rms_g",
                    "vibration_peak_g",
                    "dominant_frequency_Hz",
                    "shaft_frequency_Hz",
                )
                if _abnormal(evaluation, name)
            ]
            return DiagnosticResult(
                "fan_imbalance",
                "Abnormal vibration",
                evidence,
                "LOW",
                "Elevated vibration detected. Inspect fan mounting, blade balance and mechanical condition.",
            )

        return DiagnosticResult(
            key="normal_operation",
            suspected_fault="Normal operation",
            evidence=["No configured fault rule is active"],
            confidence="HIGH",
            recommended_action="System operating normally. Continue monitoring.",
        )
