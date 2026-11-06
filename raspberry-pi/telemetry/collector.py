"""Compatibility import for the live hardware acquisition layer.

The earlier environment-value collector has intentionally been retired from the
runtime path. Production acquisition is implemented in :mod:`sensors` and never
creates fabricated sensor readings.
"""

from sensors.acquisition import SensorAcquisition, build_sensor_acquisition

__all__ = ["SensorAcquisition", "build_sensor_acquisition"]
