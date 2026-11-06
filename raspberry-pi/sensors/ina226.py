"""INA226 adapter preserving the proven bus/shunt register calculation."""

from typing import Any, Optional


class INA226Sensor:
    _REG_SHUNT_VOLTAGE = 0x01
    _REG_BUS_VOLTAGE = 0x02

    def __init__(
        self,
        i2c_bus: int,
        address: int,
        shunt_resistance_ohm: float,
        bus: Optional[Any] = None,
    ) -> None:
        if shunt_resistance_ohm <= 0:
            raise ValueError("INA226 shunt resistance must be positive")
        if bus is None:
            from smbus2 import SMBus

            bus = SMBus(i2c_bus)
        self._bus = bus
        self._address = address
        self._shunt_resistance_ohm = shunt_resistance_ohm

    @staticmethod
    def _swap_word(value: int) -> int:
        return ((value & 0xFF) << 8) | ((value >> 8) & 0xFF)

    def _read_u16(self, register: int) -> int:
        return self._swap_word(self._bus.read_word_data(self._address, register))

    def _read_i16(self, register: int) -> int:
        value = self._read_u16(register)
        return value - 65536 if value & 0x8000 else value

    def read(self) -> "ElectricalReading":
        """Derive current from measured shunt voltage as in the live script."""

        from .models import ElectricalReading

        voltage_v = self._read_u16(self._REG_BUS_VOLTAGE) * 0.00125
        shunt_voltage_v = self._read_i16(self._REG_SHUNT_VOLTAGE) * 0.0000025
        current_a = abs(shunt_voltage_v / self._shunt_resistance_ohm)
        power_w = voltage_v * current_a
        return ElectricalReading(
            voltage_v=voltage_v,
            current_a=current_a,
            power_w=power_w,
        )

    def close(self) -> None:
        close = getattr(self._bus, "close", None)
        if callable(close):
            close()
