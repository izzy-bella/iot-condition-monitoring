"""Windowed vibration features preserving the proven NumPy FFT/RPM method."""

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import numpy as np

from sensors.models import AccelerometerWindow


@dataclass(frozen=True)
class VibrationFeatures:
    accel_x_g: float
    accel_y_g: float
    accel_z_g: float
    resultant_acceleration_g: float
    vibration_rms_g: float
    vibration_peak_g: float
    crest_factor: float
    kurtosis: float
    shaft_frequency_hz: float
    rpm: float
    blade_pass_frequency_hz: float
    dominant_frequency_hz: float
    dominant_frequency_amplitude_g: float
    actual_sample_rate_hz: float


def _dominant_frequency(
    frequencies: np.ndarray,
    amplitudes: np.ndarray,
) -> Tuple[float, float]:
    if len(frequencies) < 2:
        raise ValueError("Frequency analysis did not produce a non-DC bin")
    index = int(np.argmax(amplitudes[1:])) + 1
    return float(frequencies[index]), float(amplitudes[index])


def _shaft_and_blade_pass_frequency(
    frequencies: np.ndarray,
    amplitudes: np.ndarray,
    number_of_blades: int,
    shaft_search_low_hz: float,
    shaft_search_high_hz: float,
    blade_pass_tolerance_hz: float,
) -> Tuple[float, float]:
    """Preserve the live script's 1x shaft plus blade-pass validation."""

    mask = (frequencies >= shaft_search_low_hz) & (
        frequencies <= shaft_search_high_hz
    )
    candidate_frequencies = frequencies[mask]
    candidate_amplitudes = amplitudes[mask]
    if len(candidate_frequencies) == 0:
        raise RuntimeError("No frequencies found inside shaft search region")

    candidate_indices = [
        index
        for index in range(1, len(candidate_amplitudes) - 1)
        if candidate_amplitudes[index] > candidate_amplitudes[index - 1]
        and candidate_amplitudes[index] > candidate_amplitudes[index + 1]
    ]
    if not candidate_indices:
        candidate_indices = [int(np.argmax(candidate_amplitudes))]

    best_score = -1.0
    best_shaft: Optional[float] = None
    best_blade_pass: Optional[float] = None
    for index in candidate_indices:
        shaft_candidate = float(candidate_frequencies[index])
        expected_bpf = shaft_candidate * number_of_blades
        bpf_mask = (frequencies >= expected_bpf - blade_pass_tolerance_hz) & (
            frequencies <= expected_bpf + blade_pass_tolerance_hz
        )
        if not np.any(bpf_mask):
            continue
        bpf_frequencies = frequencies[bpf_mask]
        bpf_amplitudes = amplitudes[bpf_mask]
        bpf_index = int(np.argmax(bpf_amplitudes))
        score = float(candidate_amplitudes[index] + bpf_amplitudes[bpf_index])
        if score > best_score:
            best_score = score
            best_shaft = shaft_candidate
            best_blade_pass = float(bpf_frequencies[bpf_index])

    if best_shaft is None or best_blade_pass is None:
        strongest = int(np.argmax(candidate_amplitudes))
        best_shaft = float(candidate_frequencies[strongest])
        best_blade_pass = best_shaft * number_of_blades
    return best_shaft, best_blade_pass


def calculate_vibration_features(
    window: AccelerometerWindow,
    config: Optional[Dict[str, Any]] = None,
) -> VibrationFeatures:
    """Calculate all vibration and rotational features from one real window."""

    if len(window.samples) < 8:
        raise ValueError("Vibration features require at least 8 samples")
    if window.actual_sample_rate_hz <= 0:
        raise ValueError("Actual vibration sample rate must be positive")

    settings = config or {}
    number_of_blades = int(settings.get("number_of_blades", 7))
    accelerometer = settings.get("accelerometer", settings)
    shaft_low = float(accelerometer.get("shaft_search_low_Hz", 80.0))
    shaft_high = float(accelerometer.get("shaft_search_high_Hz", 120.0))
    bpf_tolerance = float(
        accelerometer.get("blade_pass_tolerance_Hz", 15.0)
    )
    if number_of_blades <= 0 or shaft_low >= shaft_high or bpf_tolerance <= 0:
        raise ValueError("Invalid fan or shaft-frequency processing configuration")

    x = np.asarray([sample.accel_x_g for sample in window.samples], dtype=float)
    y = np.asarray([sample.accel_y_g for sample in window.samples], dtype=float)
    z = np.asarray([sample.accel_z_g for sample in window.samples], dtype=float)
    magnitude = np.sqrt(x * x + y * y + z * z)

    # Preserve the live script's gravity/DC removal from resultant magnitude.
    vibration = magnitude - np.mean(magnitude)
    mean_square = float(np.mean(vibration ** 2))
    vibration_rms = float(np.sqrt(mean_square))
    vibration_peak = float(np.max(np.abs(vibration)))
    crest_factor = vibration_peak / vibration_rms if vibration_rms > 0 else 0.0
    fourth_moment = float(np.mean(vibration ** 4))
    kurtosis = fourth_moment / (mean_square ** 2) if mean_square > 0 else 0.0

    windowed_signal = vibration * np.hanning(len(vibration))
    fft_values = np.fft.rfft(windowed_signal)
    frequencies = np.fft.rfftfreq(
        len(vibration), d=1.0 / window.actual_sample_rate_hz
    )
    amplitudes = np.abs(fft_values)

    dominant_frequency, dominant_amplitude = _dominant_frequency(
        frequencies, amplitudes
    )
    shaft_frequency, blade_pass_frequency = _shaft_and_blade_pass_frequency(
        frequencies=frequencies,
        amplitudes=amplitudes,
        number_of_blades=number_of_blades,
        shaft_search_low_hz=shaft_low,
        shaft_search_high_hz=shaft_high,
        blade_pass_tolerance_hz=bpf_tolerance,
    )
    latest = window.samples[-1]
    return VibrationFeatures(
        accel_x_g=latest.accel_x_g,
        accel_y_g=latest.accel_y_g,
        accel_z_g=latest.accel_z_g,
        resultant_acceleration_g=float(magnitude[-1]),
        vibration_rms_g=vibration_rms,
        vibration_peak_g=vibration_peak,
        crest_factor=crest_factor,
        kurtosis=kurtosis,
        shaft_frequency_hz=shaft_frequency,
        rpm=shaft_frequency * 60.0,
        blade_pass_frequency_hz=blade_pass_frequency,
        dominant_frequency_hz=dominant_frequency,
        dominant_frequency_amplitude_g=dominant_amplitude,
        actual_sample_rate_hz=window.actual_sample_rate_hz,
    )
