"""Dependency-free tests for the shared reading and failure isolation."""

from datetime import datetime, timezone
import math
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock


RASPBERRY_PI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RASPBERRY_PI_ROOT))

from telemetry.fanout import TelemetryFanout  # noqa: E402
from telemetry.models import TelemetryReading  # noqa: E402
from main import build_publishers  # noqa: E402
from configuration import (  # noqa: E402
    RASPBERRY_PI_ENV_FILE,
    load_runtime_environment,
)
from diagnostics.condition_evaluator import (  # noqa: E402
    ConditionEvaluator,
    ConditionStatus,
)
from processing.vibration import calculate_vibration_features  # noqa: E402
from sensors.adxl345 import ADXL345Sensor  # noqa: E402
from sensors.ina226 import INA226Sensor  # noqa: E402
from sensors.models import (  # noqa: E402
    AccelerometerWindow,
    ElectricalReading,
    RawAccelerationSample,
    SensorSnapshot,
)
from storage.event_history import FaultEventTracker  # noqa: E402


class RecordingPublisher:
    def __init__(self, name: str, error: Exception = None) -> None:
        self.name = name
        self.error = error
        self.received = []

    def publish(self, reading: TelemetryReading) -> None:
        self.received.append(reading)
        if self.error is not None:
            raise self.error

    def close(self) -> None:
        return None


class TelemetryReadingTests(unittest.TestCase):
    def test_external_payload_uses_required_field_names(self) -> None:
        reading = TelemetryReading(
            device_id="fan-monitor-pi",
            temperature_c=19.0,
            voltage_v=12.059,
            current_a=0.881,
            power_w=10.63,
            observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

        self.assertEqual(
            reading.to_payload(),
            {
                "deviceId": "fan-monitor-pi",
                "timestamp": "2026-01-01T00:00:00Z",
                "temperature_C": 19.0,
                "voltage_V": 12.059,
                "current_A": 0.881,
                "power_W": 10.63,
            },
        )

    def test_non_finite_reading_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            TelemetryReading(
                device_id="fan-monitor-pi",
                temperature_c=float("nan"),
                voltage_v=12.0,
                current_a=0.8,
                power_w=9.6,
            )

    def test_rotational_feature_field_names_match_live_contract(self) -> None:
        reading = TelemetryReading(
            device_id="fan-monitor-pi",
            observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            shaft_frequency_hz=101.7,
            rpm=6102.0,
            blade_pass_frequency_hz=711.9,
            dominant_frequency_hz=711.9,
        )

        payload = reading.to_payload()
        self.assertEqual(payload["shaft_frequency_Hz"], 101.7)
        self.assertEqual(payload["rpm"], 6102.0)
        self.assertEqual(payload["blade_pass_frequency_Hz"], 711.9)
        self.assertEqual(payload["dominant_frequency_Hz"], 711.9)


class TelemetryFanoutTests(unittest.TestCase):
    def test_one_destination_failure_does_not_block_the_other(self) -> None:
        reading = TelemetryReading(
            device_id="fan-monitor-pi",
            temperature_c=19.0,
            voltage_v=12.059,
            current_a=0.881,
            power_w=10.63,
        )
        failing = RecordingPublisher("azure", RuntimeError("offline"))
        healthy = RecordingPublisher("influxdb")
        fanout = TelemetryFanout([failing, healthy], timeout_seconds=1)

        try:
            results = fanout.publish(reading)
        finally:
            fanout.close()

        result_by_destination = {result.destination: result for result in results}
        self.assertFalse(result_by_destination["azure"].succeeded)
        self.assertTrue(result_by_destination["influxdb"].succeeded)
        self.assertIs(failing.received[0], reading)
        self.assertIs(healthy.received[0], reading)


class PublisherConfigurationTests(unittest.TestCase):
    def test_missing_azure_configuration_does_not_disable_influxdb(self) -> None:
        publishers = build_publishers(
            {
                "AZURE_IOT_ENABLED": "true",
                "INFLUXDB_ENABLED": "true",
                "INFLUXDB_URL": "http://localhost:8086",
                "INFLUXDB_TOKEN": "test-placeholder",
                "INFLUXDB_ORG": "test-org",
                "INFLUXDB_BUCKET": "test-bucket",
            }
        )

        self.assertEqual([publisher.name for publisher in publishers], ["influxdb"])
        self.assertEqual(publishers[0]._measurement, "fan_condition")

    def test_missing_influxdb_configuration_does_not_disable_azure(self) -> None:
        publishers = build_publishers(
            {
                "AZURE_IOT_ENABLED": "true",
                "AZURE_IOT_DEVICE_CONNECTION_STRING": "placeholder",
                "INFLUXDB_ENABLED": "true",
            }
        )

        self.assertEqual(
            [publisher.name for publisher in publishers],
            ["azure_iot_hub"],
        )


class RuntimeEnvironmentTests(unittest.TestCase):
    def test_default_secret_path_is_the_raspberry_pi_home_file(self) -> None:
        self.assertEqual(RASPBERRY_PI_ENV_FILE, Path("/home/isabella/.env"))

    def test_dotenv_loader_does_not_override_exported_values(self) -> None:
        calls = []
        fake_dotenv = types.ModuleType("dotenv")

        def fake_load_dotenv(dotenv_path, override):
            calls.append((dotenv_path, override))
            return True

        fake_dotenv.load_dotenv = fake_load_dotenv
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("INFLUXDB_URL=https://example.invalid\n", encoding="utf-8")
            with mock.patch.dict(sys.modules, {"dotenv": fake_dotenv}):
                load_runtime_environment(env_file)

        self.assertEqual(calls, [(env_file, False)])


class VibrationProcessingTests(unittest.TestCase):
    def test_features_are_calculated_from_a_real_window(self) -> None:
        sample_rate = 200.0
        sample_count = 256
        samples = tuple(
            RawAccelerationSample(
                timestamp=datetime.fromtimestamp(index / sample_rate, tz=timezone.utc),
                accel_x_g=0.0,
                accel_y_g=0.0,
                accel_z_g=1.0 + 0.05 * math.sin(2 * math.pi * 20 * index / sample_rate),
            )
            for index in range(sample_count)
        )
        features = calculate_vibration_features(
            AccelerometerWindow(samples, sample_rate, sample_rate)
        )

        self.assertAlmostEqual(features.vibration_rms_g, 0.05 / math.sqrt(2), places=3)
        self.assertAlmostEqual(features.crest_factor, math.sqrt(2), places=1)
        self.assertAlmostEqual(features.kurtosis, 1.5, places=1)
        self.assertAlmostEqual(features.dominant_frequency_hz, 20.0, delta=1.0)

    def test_proven_shaft_rpm_and_seven_blade_bpf_logic_is_retained(self) -> None:
        sample_rate = 3200.0
        sample_count = 3200
        samples = tuple(
            RawAccelerationSample(
                timestamp=datetime.fromtimestamp(index / sample_rate, tz=timezone.utc),
                accel_x_g=0.0,
                accel_y_g=0.0,
                accel_z_g=(
                    1.0
                    + 0.03 * math.sin(2 * math.pi * 100 * index / sample_rate)
                    + 0.05 * math.sin(2 * math.pi * 700 * index / sample_rate)
                ),
            )
            for index in range(sample_count)
        )
        features = calculate_vibration_features(
            AccelerometerWindow(samples, sample_rate, sample_rate),
            {
                "number_of_blades": 7,
                "accelerometer": {
                    "shaft_search_low_Hz": 80,
                    "shaft_search_high_Hz": 120,
                    "blade_pass_tolerance_Hz": 15,
                },
            },
        )

        self.assertAlmostEqual(features.shaft_frequency_hz, 100.0, delta=1.0)
        self.assertAlmostEqual(features.rpm, 6000.0, delta=60.0)
        self.assertAlmostEqual(features.blade_pass_frequency_hz, 700.0, delta=1.0)
        self.assertAlmostEqual(features.dominant_frequency_hz, 700.0, delta=1.0)


class ProvenHardwareAdapterTests(unittest.TestCase):
    def test_adxl345_spi_commands_and_scale_match_working_script(self) -> None:
        class FakeSPI:
            max_speed_hz = 0
            mode = 0

            def __init__(self) -> None:
                self.commands = []

            def xfer2(self, command):
                self.commands.append(command)
                if command == [0x80, 0x00]:
                    return [0, 0xE5]
                if command[0] == 0xF2:
                    # X=256, Y=-256, Z=0.
                    return [0, 0x00, 0x01, 0x00, 0xFF, 0x00, 0x00]
                return [0 for _ in command]

        spi = FakeSPI()
        sensor = ADXL345Sensor(
            spi_bus=0,
            spi_device=0,
            spi_speed_hz=2_000_000,
            sample_rate_hz=8,
            window_seconds=1,
            spi=spi,
        )
        x_g, y_g, z_g = sensor.read_xyz()

        self.assertEqual(spi.mode, 0b11)
        self.assertEqual(spi.max_speed_hz, 2_000_000)
        self.assertIn([0x31, 0x0B], spi.commands)
        self.assertIn([0x2C, 0x0F], spi.commands)
        self.assertIn([0x2D, 0x08], spi.commands)
        self.assertAlmostEqual(x_g, 0.9984, places=4)
        self.assertAlmostEqual(y_g, -0.9984, places=4)
        self.assertEqual(z_g, 0.0)

    def test_ina226_uses_working_shunt_voltage_calculation(self) -> None:
        class FakeBus:
            def read_word_data(self, _address, register):
                # Values are byte-swapped as returned by SMBus word access.
                return {0x02: 0x8025, 0x01: 0x4006}[register]

        reading = INA226Sensor(
            i2c_bus=1,
            address=0x41,
            shunt_resistance_ohm=0.005,
            bus=FakeBus(),
        ).read()

        self.assertAlmostEqual(reading.voltage_v, 12.0, places=3)
        self.assertAlmostEqual(reading.current_a, 0.8, places=3)
        self.assertAlmostEqual(reading.power_w, 9.6, places=3)


class ConditionEvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.thresholds = {
            "stale_timeout_seconds": 30,
            "temperature_C": {"warning_high": 35.0, "critical_high": 45.0},
            "current_A": {
                "normal_low": 0.5,
                "warning_high": 0.95,
                "critical_high": 1.10,
            },
            "voltage_V": {},
            "power_W": {},
            "vibration_rms_g": {},
            "vibration_peak_g": {},
            "crest_factor": {},
            "kurtosis": {},
            "dominant_frequency_Hz": {},
        }

    def test_warning_current_boundary_is_explicit(self) -> None:
        now = datetime.now(timezone.utc)
        snapshot = SensorSnapshot(
            device_id="fan-monitor-pi",
            timestamp=now,
            temperature_c=19.0,
            electrical=ElectricalReading(12.0, 0.95, 11.4),
        )
        result = ConditionEvaluator(self.thresholds).evaluate(snapshot, None, now=now)
        self.assertEqual(result.metrics["current_A"].status, ConditionStatus.WARNING)

    def test_stale_data_is_offline(self) -> None:
        observed = datetime(2026, 1, 1, tzinfo=timezone.utc)
        current = datetime(2026, 1, 1, 0, 0, 31, tzinfo=timezone.utc)
        snapshot = SensorSnapshot(device_id="fan-monitor-pi", timestamp=observed)
        result = ConditionEvaluator(self.thresholds).evaluate(snapshot, None, now=current)
        self.assertEqual(result.status, ConditionStatus.OFFLINE)


class EventHistoryTests(unittest.TestCase):
    def test_persistent_fault_creates_one_start_and_one_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tracker = FaultEventTracker(str(Path(directory) / "events.db"))
            warning = TelemetryReading(
                device_id="fan-monitor-pi",
                condition_status="WARNING",
                suspected_fault="Overheating",
                diagnostic_evidence="temperature high",
                fmeca_severity=8,
                fmeca_rpn=48,
                maintenance_priority="HIGH",
                recommended_action="Inspect airflow",
            )
            normal = TelemetryReading(
                device_id="fan-monitor-pi",
                condition_status="NORMAL",
                suspected_fault="Normal operation",
            )
            try:
                first = tracker.update(warning)
                repeated = tracker.update(warning)
                resolved = tracker.update(normal)
            finally:
                tracker.close()

        self.assertEqual([item["event_state"] for item in first], ["STARTED"])
        self.assertEqual(repeated, tuple())
        self.assertEqual([item["event_state"] for item in resolved], ["RESOLVED"])


if __name__ == "__main__":
    unittest.main()
