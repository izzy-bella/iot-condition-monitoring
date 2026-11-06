"""ADXL345 SPI adapter based on the proven Raspberry Pi acquisition script."""

from datetime import datetime, timedelta, timezone
import time
from typing import Any, List, Optional, Tuple

from .models import AccelerometerWindow, RawAccelerationSample


class ADXL345Sensor:
    """Acquire one unpaced high-rate ADXL345 window over SPI.

    The register commands, SPI mode, full-resolution scale and 3200 Hz ADXL345
    configuration intentionally match the supplied working hardware script.
    ``sample_rate_hz`` is the previously measured acquisition rate used only to
    choose the requested sample count. Frequency bins use the measured rate.
    """

    _EXPECTED_DEVICE_ID = 0xE5
    _SCALE_G_PER_LSB = 0.0039

    def __init__(
        self,
        spi_bus: int,
        spi_device: int,
        spi_speed_hz: int,
        sample_rate_hz: float,
        window_seconds: float,
        mode: int = 0b11,
        spi: Optional[Any] = None,
    ) -> None:
        if spi_bus < 0 or spi_device < 0:
            raise ValueError("SPI bus and device must be non-negative")
        if spi_speed_hz <= 0 or sample_rate_hz <= 0 or window_seconds <= 0:
            raise ValueError("SPI speed, sample rate and window duration must be positive")
        if mode not in range(4):
            raise ValueError("SPI mode must be between 0 and 3")

        if spi is None:
            import spidev

            spi = spidev.SpiDev()
            spi.open(spi_bus, spi_device)
        self._spi = spi
        self._spi.max_speed_hz = spi_speed_hz
        self._spi.mode = mode
        self._requested_sample_rate_hz = float(sample_rate_hz)
        self._sample_count = int(sample_rate_hz * window_seconds)
        if self._sample_count < 8:
            raise ValueError("ADXL345 window must contain at least 8 samples")

        device_id = self._spi.xfer2([0x80, 0x00])[1]
        if device_id != self._EXPECTED_DEVICE_ID:
            raise RuntimeError(
                "ADXL345 device ID mismatch: expected 0xE5, got 0x{:02X}".format(
                    device_id
                )
            )

        self._write_register(0x31, 0x0B)  # Full resolution, +/-16 g.
        self._write_register(0x2C, 0x0F)  # 3200 Hz output data rate.
        self._write_register(0x2D, 0x08)  # Measurement mode.
        time.sleep(0.1)

    def _write_register(self, register: int, value: int) -> None:
        self._spi.xfer2([register & 0x3F, value])

    @staticmethod
    def _decode_i16(low: int, high: int) -> int:
        value = low | (high << 8)
        return value - 65536 if value & 0x8000 else value

    def read_xyz(self) -> Tuple[float, float, float]:
        """Read one XYZ sample using the working multi-byte SPI command."""

        response: List[int] = self._spi.xfer2([0xF2, 0, 0, 0, 0, 0, 0])
        if len(response) != 7:
            raise RuntimeError("ADXL345 SPI read returned an incomplete sample")
        return (
            self._decode_i16(response[1], response[2]) * self._SCALE_G_PER_LSB,
            self._decode_i16(response[3], response[4]) * self._SCALE_G_PER_LSB,
            self._decode_i16(response[5], response[6]) * self._SCALE_G_PER_LSB,
        )

    def read_window(self) -> AccelerometerWindow:
        """Read the same approximately one-second unpaced window as the live script."""

        captured: List[Tuple[float, float, float]] = []
        started_at = datetime.now(timezone.utc)
        started_monotonic = time.perf_counter()
        for _ in range(self._sample_count):
            captured.append(self.read_xyz())
        elapsed = time.perf_counter() - started_monotonic
        if elapsed <= 0:
            raise RuntimeError("ADXL345 acquisition elapsed time was not positive")

        actual_rate = self._sample_count / elapsed
        # Generate evenly spaced UTC times after acquisition. This avoids a
        # datetime system call inside every SPI transaction and preserves the
        # measured high-rate acquisition behavior.
        samples = tuple(
            RawAccelerationSample(
                timestamp=started_at + timedelta(seconds=index / actual_rate),
                accel_x_g=values[0],
                accel_y_g=values[1],
                accel_z_g=values[2],
            )
            for index, values in enumerate(captured)
        )
        return AccelerometerWindow(
            samples=samples,
            requested_sample_rate_hz=self._requested_sample_rate_hz,
            actual_sample_rate_hz=actual_rate,
        )

    def close(self) -> None:
        close = getattr(self._spi, "close", None)
        if callable(close):
            close()
