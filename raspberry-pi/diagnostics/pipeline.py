"""End-to-end processing from raw snapshot to complete monitoring telemetry."""

from collections import deque
from dataclasses import replace
from typing import Any, Deque, Dict, Optional

from processing.vibration import VibrationFeatures, calculate_vibration_features
from sensors.models import SensorSnapshot
from telemetry.models import TelemetryReading

from .condition_evaluator import ConditionEvaluator, ConditionStatus
from .fault_detector import FaultDetector
from .fmeca import FMECAEvaluator
from .health_score import HealthScoreCalculator


CONDITION_CODES = {
    ConditionStatus.NORMAL: 0,
    ConditionStatus.WARNING: 1,
    ConditionStatus.CRITICAL: 2,
    ConditionStatus.OFFLINE: 3,
}


class DiagnosticPipeline:
    def __init__(
        self,
        thresholds: Dict[str, Any],
        fmeca: Dict[str, Any],
        sensor_config: Optional[Dict[str, Any]] = None,
        baseline_acquisition_mode: bool = False,
    ) -> None:
        self._thresholds = thresholds
        self._sensor_config = sensor_config or {}
        self._baseline_acquisition_mode = baseline_acquisition_mode
        self._condition_evaluator = ConditionEvaluator(thresholds)
        self._fault_detector = FaultDetector()
        self._fmeca = FMECAEvaluator(fmeca)
        self._health = HealthScoreCalculator(thresholds["health_score"])
        trend_count = int(thresholds.get("vibration_trend", {}).get("window_count", 6))
        self._rms_history: Deque[float] = deque(maxlen=max(2, trend_count))

    def _vibration_increasing(self) -> bool:
        config = self._thresholds.get("vibration_trend", {})
        warning_fraction = config.get("warning_fraction_increase")
        if warning_fraction is None or len(self._rms_history) < self._rms_history.maxlen:
            return False
        baseline = self._rms_history[0]
        if baseline <= 0:
            return False
        return (self._rms_history[-1] - baseline) / baseline >= float(warning_fraction)

    def process(self, snapshot: SensorSnapshot) -> TelemetryReading:
        vibration: Optional[VibrationFeatures] = None
        if snapshot.acceleration is not None:
            try:
                vibration = calculate_vibration_features(
                    snapshot.acceleration,
                    self._sensor_config,
                )
                self._rms_history.append(vibration.vibration_rms_g)
            except Exception as exc:
                errors = dict(snapshot.errors)
                errors["vibration_processing"] = str(exc)
                snapshot = replace(snapshot, errors=errors)

        evaluation = self._condition_evaluator.evaluate(snapshot, vibration)
        diagnostic = self._fault_detector.diagnose(
            snapshot,
            vibration,
            evaluation,
            vibration_increasing=self._vibration_increasing(),
        )
        fmeca = self._fmeca.assess(
            diagnostic.key,
            diagnostic.recommended_action,
        )
        health_score = self._health.calculate(
            evaluation,
            evaluation.status,
            len(snapshot.errors),
        )
        electrical = snapshot.electrical

        metric = evaluation.metrics.get
        return TelemetryReading(
            device_id=snapshot.device_id,
            observed_at=snapshot.timestamp,
            temperature_c=snapshot.temperature_c,
            temperature_observed_at=snapshot.temperature_observed_at,
            voltage_v=electrical.voltage_v if electrical else None,
            current_a=electrical.current_a if electrical else None,
            power_w=electrical.power_w if electrical else None,
            accel_x_g=vibration.accel_x_g if vibration else None,
            accel_y_g=vibration.accel_y_g if vibration else None,
            accel_z_g=vibration.accel_z_g if vibration else None,
            resultant_acceleration_g=(
                vibration.resultant_acceleration_g if vibration else None
            ),
            vibration_rms_g=vibration.vibration_rms_g if vibration else None,
            vibration_peak_g=vibration.vibration_peak_g if vibration else None,
            crest_factor=vibration.crest_factor if vibration else None,
            kurtosis=vibration.kurtosis if vibration else None,
            shaft_frequency_hz=(
                vibration.shaft_frequency_hz if vibration else None
            ),
            rpm=vibration.rpm if vibration else None,
            blade_pass_frequency_hz=(
                vibration.blade_pass_frequency_hz if vibration else None
            ),
            dominant_frequency_hz=(
                vibration.dominant_frequency_hz if vibration else None
            ),
            dominant_frequency_amplitude_g=(
                vibration.dominant_frequency_amplitude_g if vibration else None
            ),
            vibration_sample_rate_hz=(
                vibration.actual_sample_rate_hz if vibration else None
            ),
            condition_status=evaluation.status.value,
            condition_code=CONDITION_CODES[evaluation.status],
            suspected_fault=diagnostic.suspected_fault,
            diagnostic_evidence="; ".join(diagnostic.evidence),
            diagnostic_confidence=diagnostic.confidence,
            health_score=health_score,
            fmeca_rpn=fmeca.rpn,
            fmeca_severity=fmeca.severity,
            fmeca_occurrence=fmeca.occurrence,
            fmeca_detectability=fmeca.detectability,
            maintenance_priority=fmeca.maintenance_priority,
            recommended_action=(
                "Critical operating condition detected. Stop and inspect the fan system."
                if evaluation.status == ConditionStatus.CRITICAL
                else (
                    "Baseline acquisition active. Continue collecting real normal-operation data."
                    if self._baseline_acquisition_mode
                    and evaluation.status == ConditionStatus.NORMAL
                    else fmeca.recommended_action
                )
            ),
            baseline_acquisition_mode=self._baseline_acquisition_mode,
            temperature_status_code=(metric("temperature_C").code if metric("temperature_C") else None),
            current_status_code=(metric("current_A").code if metric("current_A") else None),
            voltage_status_code=(metric("voltage_V").code if metric("voltage_V") else None),
            power_status_code=(metric("power_W").code if metric("power_W") else None),
            vibration_rms_status_code=(metric("vibration_rms_g").code if metric("vibration_rms_g") else None),
            vibration_peak_status_code=(metric("vibration_peak_g").code if metric("vibration_peak_g") else None),
            crest_factor_status_code=(metric("crest_factor").code if metric("crest_factor") else None),
            kurtosis_status_code=(metric("kurtosis").code if metric("kurtosis") else None),
            shaft_frequency_status_code=(
                metric("shaft_frequency_Hz").code
                if metric("shaft_frequency_Hz")
                else None
            ),
            raw_acceleration_samples=(
                snapshot.acceleration.samples if snapshot.acceleration else tuple()
            ),
        )
