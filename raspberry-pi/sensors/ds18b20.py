"""DS18B20 temperature sensor using the Raspberry Pi 1-Wire sysfs interface."""

from glob import glob
import time
from typing import List


class DS18B20Sensor:
    def __init__(self, device_glob: str, crc_retries: int = 3) -> None:
        if crc_retries < 1:
            raise ValueError("crc_retries must be at least one")
        self._device_glob = device_glob
        self._crc_retries = crc_retries

    def _device_path(self) -> str:
        matches: List[str] = sorted(glob(self._device_glob))
        if not matches:
            raise RuntimeError(
                "No DS18B20 device matched {}".format(self._device_glob)
            )
        if len(matches) > 1:
            raise RuntimeError(
                "Multiple DS18B20 devices matched; configure one explicit path"
            )
        return matches[0]

    def read_temperature_c(self) -> float:
        path = self._device_path()
        last_error = "unknown DS18B20 read error"
        for attempt in range(self._crc_retries):
            with open(path, "r", encoding="ascii") as handle:
                lines = handle.read().strip().splitlines()
            if len(lines) >= 2 and lines[0].strip().endswith("YES"):
                marker = lines[1].find("t=")
                if marker >= 0:
                    return float(lines[1][marker + 2 :]) / 1000.0
                last_error = "DS18B20 response did not contain t="
            else:
                last_error = "DS18B20 CRC check failed"
            if attempt + 1 < self._crc_retries:
                time.sleep(0.2)
        raise RuntimeError(last_error)
