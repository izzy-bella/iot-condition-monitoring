"""Failure-isolated delivery of one reading to multiple destinations."""

from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
import logging
from typing import Dict, Iterable, List, Optional, Protocol

from .models import TelemetryReading


class TelemetryPublisher(Protocol):
    name: str

    def publish(self, reading: TelemetryReading) -> None:
        ...

    def close(self) -> None:
        ...


@dataclass(frozen=True)
class PublishResult:
    destination: str
    succeeded: bool
    error: Optional[str] = None


class TelemetryFanout:
    """Send the same object concurrently so either destination may fail alone."""

    def __init__(
        self,
        publishers: Iterable[TelemetryPublisher],
        timeout_seconds: float = 10.0,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._publishers: List[TelemetryPublisher] = list(publishers)
        if not self._publishers:
            raise ValueError("At least one telemetry publisher must be configured")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._timeout_seconds = timeout_seconds
        self._logger = logger or logging.getLogger(__name__)
        # Keep a dedicated worker for each destination. A stalled Azure call
        # therefore cannot occupy the worker needed by InfluxDB, or vice versa.
        self._executors: Dict[str, ThreadPoolExecutor] = {
            publisher.name: ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="telemetry-{}".format(publisher.name),
            )
            for publisher in self._publishers
        }

    def publish(self, reading: TelemetryReading) -> List[PublishResult]:
        future_to_publisher: Dict[Future[None], TelemetryPublisher] = {
            self._executors[publisher.name].submit(
                publisher.publish,
                reading,
            ): publisher
            for publisher in self._publishers
        }
        done, pending = wait(
            future_to_publisher,
            timeout=self._timeout_seconds,
        )

        results: List[PublishResult] = []
        for future in done:
            publisher = future_to_publisher[future]
            try:
                future.result()
            except Exception as exc:  # Destination faults must not escape the fan-out.
                self._logger.error(
                    "Telemetry publish failed for %s: %s",
                    publisher.name,
                    exc,
                )
                results.append(
                    PublishResult(
                        destination=publisher.name,
                        succeeded=False,
                        error=str(exc),
                    )
                )
            else:
                results.append(
                    PublishResult(destination=publisher.name, succeeded=True)
                )

        for future in pending:
            publisher = future_to_publisher[future]
            future.cancel()
            message = "publish timed out after {:.1f}s".format(self._timeout_seconds)
            self._logger.error("%s for %s", message, publisher.name)
            results.append(
                PublishResult(
                    destination=publisher.name,
                    succeeded=False,
                    error=message,
                )
            )

        return sorted(results, key=lambda result: result.destination)

    def close(self) -> None:
        for publisher in self._publishers:
            try:
                publisher.close()
            except Exception as exc:
                self._logger.error(
                    "Telemetry publisher shutdown failed for %s: %s",
                    publisher.name,
                    exc,
                )
        for executor in self._executors.values():
            executor.shutdown(wait=False, cancel_futures=True)
