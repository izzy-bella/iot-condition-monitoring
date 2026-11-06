"""Raw sensor-domain models, kept separate from derived vibration features."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class ElectricalReading:
    voltage_v: float
    current_a: float
    power_w: float


@dataclass(frozen=True)
class RawAccelerationSample:
    timestamp: datetime
    accel_x_g: float
    accel_y_g: float
    accel_z_g: float


@dataclass(frozen=True)
class AccelerometerWindow:
    samples: Tuple[RawAccelerationSample, ...]
    requested_sample_rate_hz: float
    actual_sample_rate_hz: float


@dataclass(frozen=True)
class SensorSnapshot:
    device_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    temperature_c: Optional[float] = None
    electrical: Optional[ElectricalReading] = None
    acceleration: Optional[AccelerometerWindow] = None
    errors: Dict[str, str] = field(default_factory=dict)
    fan_expected_running: bool = True
