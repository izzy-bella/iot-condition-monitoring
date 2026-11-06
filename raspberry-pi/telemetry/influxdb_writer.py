"""InfluxDB destination adapter for summary, raw vibration and event data."""

from typing import Any, Optional

from .models import TelemetryReading


class InfluxDBWriter:
    """Write one shared reading using query-efficient measurements."""

    name = "influxdb"

    def __init__(
        self,
        url: str,
        token: str,
        org: str,
        bucket: str,
        measurement: str = "fan_condition",
        timeout_ms: int = 5000,
    ) -> None:
        required = {
            "INFLUXDB_URL": url,
            "INFLUXDB_TOKEN": token,
            "INFLUXDB_ORG": org,
            "INFLUXDB_BUCKET": bucket,
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise ValueError(
                "Missing InfluxDB configuration: {}".format(", ".join(missing))
            )
        if not measurement.strip():
            raise ValueError("INFLUXDB_MEASUREMENT must not be empty")

        self._url = url
        self._token = token
        self._org = org
        self._bucket = bucket
        self._measurement = measurement
        self._timeout_ms = timeout_ms
        self._client: Optional[Any] = None
        self._write_api: Optional[Any] = None
        self._point_class: Optional[Any] = None
        self._write_precision: Optional[Any] = None

    def _connect(self) -> None:
        if self._client is not None:
            return

        from influxdb_client import InfluxDBClient, Point, WritePrecision
        from influxdb_client.client.write_api import SYNCHRONOUS

        client = InfluxDBClient(
            url=self._url,
            token=self._token,
            org=self._org,
            timeout=self._timeout_ms,
        )
        self._client = client
        self._write_api = client.write_api(write_options=SYNCHRONOUS)
        self._point_class = Point
        self._write_precision = WritePrecision.NS

    def publish(self, reading: TelemetryReading) -> None:
        self._connect()
        assert self._write_api is not None
        assert self._point_class is not None

        summary = self._point_class(self._measurement).tag(
            "deviceId", reading.device_id
        )
        for name, value in reading.to_payload().items():
            if name in {"deviceId", "timestamp"}:
                continue
            summary = summary.field(name, value)
        summary = summary.time(reading.observed_at, self._write_precision)

        records = [summary]
        for sample in reading.raw_acceleration_samples:
            records.append(
                self._point_class("fan_vibration_raw")
                .tag("deviceId", reading.device_id)
                .field("accel_x_g", float(sample.accel_x_g))
                .field("accel_y_g", float(sample.accel_y_g))
                .field("accel_z_g", float(sample.accel_z_g))
                .time(sample.timestamp, self._write_precision)
            )

        for event in reading.event_transitions:
            event_point = (
                self._point_class("fan_condition_events")
                .tag("deviceId", reading.device_id)
                .tag("event_id", str(event["event_id"]))
                .tag("event_state", str(event["event_state"]))
            )
            for field_name in (
                "condition",
                "suspected_fault",
                "diagnostic_evidence",
                "severity",
                "fmeca_rpn",
                "maintenance_priority",
                "recommended_action",
                "started_at",
                "resolved_at",
            ):
                field_value = event.get(field_name)
                if field_value is not None:
                    event_point = event_point.field(field_name, field_value)
            records.append(event_point.time(reading.observed_at, self._write_precision))

        self._write_api.write(bucket=self._bucket, org=self._org, record=records)

    def close(self) -> None:
        try:
            if self._write_api is not None:
                self._write_api.close()
        finally:
            self._write_api = None
            if self._client is not None:
                self._client.close()
            self._client = None
            self._point_class = None
            self._write_precision = None
