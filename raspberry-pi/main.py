"""Raspberry Pi telemetry application.

One reading is collected per cycle and the exact same immutable object is sent
to Azure IoT Hub and InfluxDB through failure-isolated adapters.
"""

import argparse
from dataclasses import replace
import logging
import os
import signal
import threading
import time
from typing import List, Mapping, Optional

from configuration import load_project_configuration, load_runtime_environment
from diagnostics.pipeline import DiagnosticPipeline
from sensors.acquisition import build_sensor_acquisition
from storage.event_history import FaultEventTracker
from telemetry.azure_iot import AzureIoTPublisher
from telemetry.fanout import TelemetryFanout, TelemetryPublisher
from telemetry.influxdb_writer import InfluxDBWriter


LOGGER = logging.getLogger("fan_condition_monitoring")


def env_flag(environment: Mapping[str, str], name: str, default: bool) -> bool:
    raw_value = environment.get(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def build_publishers(
    environment: Optional[Mapping[str, str]] = None,
) -> List[TelemetryPublisher]:
    """Build each destination independently so one bad config cannot block the other."""

    env = environment if environment is not None else os.environ
    publishers: List[TelemetryPublisher] = []

    if env_flag(env, "AZURE_IOT_ENABLED", True):
        try:
            publishers.append(
                AzureIoTPublisher(
                    connection_string=env.get(
                        "AZURE_IOT_DEVICE_CONNECTION_STRING", ""
                    )
                )
            )
        except Exception as exc:
            LOGGER.error("Azure IoT publisher is unavailable: %s", exc)

    if env_flag(env, "INFLUXDB_ENABLED", True):
        try:
            publishers.append(
                InfluxDBWriter(
                    url=env.get("INFLUXDB_URL", ""),
                    token=env.get("INFLUXDB_TOKEN", ""),
                    org=env.get("INFLUXDB_ORG", ""),
                    bucket=env.get("INFLUXDB_BUCKET", ""),
                    measurement=env.get("INFLUXDB_MEASUREMENT", "fan_condition"),
                    timeout_ms=int(env.get("INFLUXDB_TIMEOUT_MS", "5000")),
                    logger=LOGGER,
                )
            )
        except Exception as exc:
            LOGGER.error("InfluxDB publisher is unavailable: %s", exc)

    return publishers


def run(once: bool = False, environment: Optional[Mapping[str, str]] = None) -> int:
    if environment is None:
        try:
            load_runtime_environment()
        except Exception as exc:
            LOGGER.error("Runtime environment loading failed: %s", exc)
            return 2

    env = environment if environment is not None else os.environ
    device_id = env.get("DEVICE_ID", "fan-monitor-pi").strip()
    if not device_id:
        LOGGER.error("DEVICE_ID is required")
        return 2

    publishers = build_publishers(env)
    if not publishers:
        LOGGER.error("No telemetry destinations are available")
        return 2

    interval_seconds = float(env.get("TELEMETRY_INTERVAL_SECONDS", "10"))
    publish_timeout_seconds = float(env.get("PUBLISH_TIMEOUT_SECONDS", "10"))
    if interval_seconds <= 0:
        LOGGER.error("TELEMETRY_INTERVAL_SECONDS must be positive")
        return 2

    try:
        configuration = load_project_configuration(env)
        acquisition = build_sensor_acquisition(
            device_id=device_id,
            config=configuration["sensors"],
            logger=LOGGER,
        )
        diagnostic_pipeline = DiagnosticPipeline(
            thresholds=configuration["thresholds"],
            fmeca=configuration["fmeca"],
            sensor_config=configuration["sensors"],
            baseline_acquisition_mode=env_flag(
                env,
                "BASELINE_ACQUISITION_MODE",
                False,
            ),
        )
    except Exception as exc:
        LOGGER.error("Monitoring pipeline initialisation failed: %s", exc)
        return 2

    event_tracker: Optional[FaultEventTracker]
    try:
        event_tracker = FaultEventTracker(
            env.get("EVENT_DB_PATH", "./data/fault_history.db")
        )
    except Exception as exc:
        event_tracker = None
        LOGGER.error(
            "Local fault history is unavailable; live publishing will continue: %s",
            exc,
        )

    fanout = TelemetryFanout(
        publishers=publishers,
        timeout_seconds=publish_timeout_seconds,
        logger=LOGGER,
    )
    stop_event = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    try:
        while not stop_event.is_set():
            cycle_started = time.monotonic()
            try:
                snapshot = acquisition.acquire()
                reading = diagnostic_pipeline.process(snapshot)
            except Exception as exc:
                LOGGER.exception("Monitoring cycle failed: %s", exc)
            else:
                if event_tracker is not None:
                    try:
                        transitions = event_tracker.update(reading)
                    except Exception as exc:
                        LOGGER.error(
                            "Fault history update failed; publishing will continue: %s",
                            exc,
                        )
                    else:
                        if transitions:
                            reading = replace(reading, event_transitions=transitions)
                results = fanout.publish(reading)
                for result in results:
                    if result.succeeded:
                        LOGGER.info(
                            "Published reading for %s to %s",
                            reading.device_id,
                            result.destination,
                        )

            if once:
                break
            elapsed = time.monotonic() - cycle_started
            stop_event.wait(max(0.0, interval_seconds - elapsed))
    finally:
        fanout.close()
        if event_tracker is not None:
            event_tracker.close()
        acquisition.close()

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--once",
        action="store_true",
        help="Collect and publish one reading, then exit.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    raise SystemExit(run(once=arguments.once))
