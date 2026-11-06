"""Azure IoT Hub destination adapter.

The Azure SDK is imported lazily so the local InfluxDB path can still start when
the Azure dependency or configuration is unavailable.
"""

import json
from typing import Any, Optional

from .models import TelemetryReading


class AzureIoTPublisher:
    """Publish the shared telemetry payload to the existing Azure IoT Hub."""

    name = "azure_iot_hub"

    def __init__(self, connection_string: str) -> None:
        if not connection_string.strip():
            raise ValueError("AZURE_IOT_DEVICE_CONNECTION_STRING is required")
        self._connection_string = connection_string
        self._client: Optional[Any] = None
        self._message_class: Optional[Any] = None

    def _connect(self) -> None:
        if self._client is not None:
            return

        from azure.iot.device import IoTHubDeviceClient, Message

        client = IoTHubDeviceClient.create_from_connection_string(
            self._connection_string
        )
        client.connect()
        self._client = client
        self._message_class = Message

    def publish(self, reading: TelemetryReading) -> None:
        self._connect()
        assert self._client is not None
        assert self._message_class is not None

        body = json.dumps(reading.to_payload(), separators=(",", ":"))
        message = self._message_class(body)
        message.content_type = "application/json"
        message.content_encoding = "utf-8"
        self._client.send_message(message)

    def close(self) -> None:
        if self._client is None:
            return
        try:
            self._client.shutdown()
        finally:
            self._client = None
            self._message_class = None
