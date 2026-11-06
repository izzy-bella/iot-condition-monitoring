"""Complete monitoring telemetry shared by Azure IoT Hub and InfluxDB."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class TelemetryReading:
    """One immutable, fully evaluated monitoring observation.

    Missing physical values remain ``None`` and are omitted from external
    payloads. They are never replaced with fabricated numbers.
    """

    device_id: str
    observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    temperature_c: Optional[float] = None
    voltage_v: Optional[float] = None
    current_a: Optional[float] = None
    power_w: Optional[float] = None

    accel_x_g: Optional[float] = None
    accel_y_g: Optional[float] = None
    accel_z_g: Optional[float] = None
    resultant_acceleration_g: Optional[float] = None
    vibration_rms_g: Optional[float] = None
    vibration_peak_g: Optional[float] = None
    crest_factor: Optional[float] = None
    kurtosis: Optional[float] = None
    shaft_frequency_hz: Optional[float] = None
    rpm: Optional[float] = None
    blade_pass_frequency_hz: Optional[float] = None
    dominant_frequency_hz: Optional[float] = None
    dominant_frequency_amplitude_g: Optional[float] = None
    vibration_sample_rate_hz: Optional[float] = None

    condition_status: Optional[str] = None
    condition_code: Optional[int] = None
    suspected_fault: Optional[str] = None
    diagnostic_evidence: Optional[str] = None
    diagnostic_confidence: Optional[str] = None
    health_score: Optional[float] = None
    fmeca_rpn: Optional[int] = None
    fmeca_severity: Optional[int] = None
    fmeca_occurrence: Optional[int] = None
    fmeca_detectability: Optional[int] = None
    maintenance_priority: Optional[str] = None
    recommended_action: Optional[str] = None
    baseline_acquisition_mode: bool = False

    temperature_status_code: Optional[int] = None
    current_status_code: Optional[int] = None
    voltage_status_code: Optional[int] = None
    power_status_code: Optional[int] = None
    vibration_rms_status_code: Optional[int] = None
    vibration_peak_status_code: Optional[int] = None
    crest_factor_status_code: Optional[int] = None
    kurtosis_status_code: Optional[int] = None
    shaft_frequency_status_code: Optional[int] = None

    raw_acceleration_samples: Tuple[Any, ...] = field(default_factory=tuple, repr=False)
    event_transitions: Tuple[Dict[str, Any], ...] = field(
        default_factory=tuple,
        repr=False,
    )

    def __post_init__(self) -> None:
        if not self.device_id.strip():
            raise ValueError("device_id must not be empty")
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at must include timezone information")

        for name, value in self._numeric_payload().items():
            if value is not None and not math.isfinite(float(value)):
                raise ValueError("{} must be a finite number".format(name))

    def _numeric_payload(self) -> Dict[str, Optional[float]]:
        return {
            "temperature_C": self.temperature_c,
            "voltage_V": self.voltage_v,
            "current_A": self.current_a,
            "power_W": self.power_w,
            "accel_x_g": self.accel_x_g,
            "accel_y_g": self.accel_y_g,
            "accel_z_g": self.accel_z_g,
            "resultant_acceleration_g": self.resultant_acceleration_g,
            "vibration_rms_g": self.vibration_rms_g,
            "vibration_peak_g": self.vibration_peak_g,
            "crest_factor": self.crest_factor,
            "kurtosis": self.kurtosis,
            "shaft_frequency_Hz": self.shaft_frequency_hz,
            "rpm": self.rpm,
            "blade_pass_frequency_Hz": self.blade_pass_frequency_hz,
            "dominant_frequency_Hz": self.dominant_frequency_hz,
            "dominant_frequency_amplitude_g": self.dominant_frequency_amplitude_g,
            "vibration_sample_rate_Hz": self.vibration_sample_rate_hz,
            "health_score": self.health_score,
        }

    def to_payload(self) -> Dict[str, Any]:
        """Return complete summary fields, omitting unavailable values."""

        payload: Dict[str, Any] = {
            "deviceId": self.device_id,
            "timestamp": self.observed_at.astimezone(timezone.utc).isoformat().replace(
                "+00:00", "Z"
            ),
        }
        payload.update(
            {
                name: float(value)
                for name, value in self._numeric_payload().items()
                if value is not None
            }
        )

        optional_values: Dict[str, Any] = {
            "condition_status": self.condition_status,
            "condition_code": self.condition_code,
            "suspected_fault": self.suspected_fault,
            "diagnostic_evidence": self.diagnostic_evidence,
            "diagnostic_confidence": self.diagnostic_confidence,
            "fmeca_rpn": self.fmeca_rpn,
            "fmeca_severity": self.fmeca_severity,
            "fmeca_occurrence": self.fmeca_occurrence,
            "fmeca_detectability": self.fmeca_detectability,
            "maintenance_priority": self.maintenance_priority,
            "recommended_action": self.recommended_action,
            "temperature_status_code": self.temperature_status_code,
            "current_status_code": self.current_status_code,
            "voltage_status_code": self.voltage_status_code,
            "power_status_code": self.power_status_code,
            "vibration_rms_status_code": self.vibration_rms_status_code,
            "vibration_peak_status_code": self.vibration_peak_status_code,
            "crest_factor_status_code": self.crest_factor_status_code,
            "kurtosis_status_code": self.kurtosis_status_code,
            "shaft_frequency_status_code": self.shaft_frequency_status_code,
        }
        payload.update(
            {name: value for name, value in optional_values.items() if value is not None}
        )
        if self.baseline_acquisition_mode:
            payload["baseline_acquisition_mode"] = True
        return payload
