"""Coordinated acquisition that preserves partial real readings and errors."""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional

from .adxl345 import ADXL345Sensor
from .ds18b20 import DS18B20Sensor
from .ina226 import INA226Sensor
from .models import AccelerometerWindow, ElectricalReading, SensorSnapshot


class SensorAcquisition:
    def __init__(
        self,
        device_id: str,
        temperature_sensor: Optional[Any],
        electrical_sensor: Optional[Any],
        accelerometer: Optional[Any],
        fan_expected_running: bool = True,
        startup_errors: Optional[Dict[str, str]] = None,
    ) -> None:
        self._device_id = device_id
        self._temperature_sensor = temperature_sensor
        self._electrical_sensor = electrical_sensor
        self._accelerometer = accelerometer
        self._fan_expected_running = fan_expected_running
        self._startup_errors = dict(startup_errors or {})

    def acquire(self) -> SensorSnapshot:
        errors = dict(self._startup_errors)
        temperature_c: Optional[float] = None
        electrical: Optional[ElectricalReading] = None
        acceleration: Optional[AccelerometerWindow] = None

        if self._temperature_sensor is not None:
            try:
                temperature_c = float(
                    self._temperature_sensor.read_temperature_c()
                )
            except Exception as exc:
                errors["temperature"] = str(exc)

        if self._electrical_sensor is not None:
            try:
                electrical = self._electrical_sensor.read()
            except Exception as exc:
                errors["electrical"] = str(exc)

        if self._accelerometer is not None:
            try:
                acceleration = self._accelerometer.read_window()
            except Exception as exc:
                errors["accelerometer"] = str(exc)

        return SensorSnapshot(
            device_id=self._device_id,
            timestamp=datetime.now(timezone.utc),
            temperature_c=temperature_c,
            electrical=electrical,
            acceleration=acceleration,
            errors=errors,
            fan_expected_running=self._fan_expected_running,
        )

    def close(self) -> None:
        for sensor in (
            self._temperature_sensor,
            self._electrical_sensor,
            self._accelerometer,
        ):
            if sensor is None:
                continue
            close = getattr(sensor, "close", None)
            if callable(close):
                close()


def build_sensor_acquisition(
    device_id: str,
    config: Dict[str, Any],
    logger: Optional[logging.Logger] = None,
) -> SensorAcquisition:
    log = logger or logging.getLogger(__name__)
    startup_errors: Dict[str, str] = {}
    temperature_sensor: Optional[Any] = None
    electrical_sensor: Optional[Any] = None
    accelerometer: Optional[Any] = None

    temperature_config = config.get("ds18b20", {})
    if temperature_config.get("enabled", True):
        try:
            temperature_sensor = DS18B20Sensor(
                device_glob=str(temperature_config["device_glob"]),
                crc_retries=int(temperature_config.get("crc_retries", 3)),
            )
        except Exception as exc:
            startup_errors["temperature"] = str(exc)
            log.error("DS18B20 initialisation failed: %s", exc)

    electrical_config = config.get("ina226", {})
    if electrical_config.get("enabled", True):
        try:
            electrical_sensor = INA226Sensor(
                i2c_bus=int(electrical_config["i2c_bus"]),
                address=int(electrical_config["address"]),
                shunt_resistance_ohm=float(
                    electrical_config["shunt_resistance_ohm"]
                ),
            )
        except Exception as exc:
            startup_errors["electrical"] = str(exc)
            log.error("INA226 initialisation failed: %s", exc)

    accelerometer_config = config.get("accelerometer", {})
    if accelerometer_config.get("enabled", True):
        model = str(accelerometer_config.get("model", "")).upper()
        if model != "ADXL345":
            startup_errors["accelerometer"] = (
                "Unsupported accelerometer model: {}".format(model)
            )
        else:
            try:
                accelerometer = ADXL345Sensor(
                    spi_bus=int(accelerometer_config["spi_bus"]),
                    spi_device=int(accelerometer_config["spi_device"]),
                    spi_speed_hz=int(accelerometer_config["spi_speed_Hz"]),
                    sample_rate_hz=float(accelerometer_config["sample_rate_Hz"]),
                    window_seconds=float(accelerometer_config["window_seconds"]),
                    mode=int(accelerometer_config.get("spi_mode", 3)),
                )
            except Exception as exc:
                startup_errors["accelerometer"] = str(exc)
                log.error("Accelerometer initialisation failed: %s", exc)

    return SensorAcquisition(
        device_id=device_id,
        temperature_sensor=temperature_sensor,
        electrical_sensor=electrical_sensor,
        accelerometer=accelerometer,
        fan_expected_running=bool(config.get("fan_expected_running", True)),
        startup_errors=startup_errors,
    )
