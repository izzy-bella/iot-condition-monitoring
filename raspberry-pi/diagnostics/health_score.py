"""Transparent weighted asset-health calculation."""

from typing import Any, Dict, Iterable, Optional

from .condition_evaluator import ConditionStatus, EvaluationResult


class HealthScoreCalculator:
    def __init__(self, config: Dict[str, Any]) -> None:
        self._config = dict(config)

    def _mean_metric_score(
        self,
        evaluation: EvaluationResult,
        metric_names: Iterable[str],
    ) -> Optional[float]:
        status_scores = self._config["status_scores"]
        scores = []
        for name in metric_names:
            metric = evaluation.metrics.get(name)
            if metric and metric.status.value in status_scores:
                scores.append(float(status_scores[metric.status.value]))
        return sum(scores) / len(scores) if scores else None

    def calculate(
        self,
        evaluation: EvaluationResult,
        diagnostic_status: ConditionStatus,
        sensor_error_count: int,
    ) -> Optional[float]:
        if evaluation.status == ConditionStatus.OFFLINE:
            return None

        components: Dict[str, Optional[float]] = {
            "temperature": self._mean_metric_score(
                evaluation, ["temperature_C"]
            ),
            "electrical": self._mean_metric_score(
                evaluation, ["voltage_V", "current_A", "power_W"]
            ),
            "vibration": self._mean_metric_score(
                evaluation,
                [
                    "vibration_rms_g",
                    "vibration_peak_g",
                    "crest_factor",
                    "kurtosis",
                    "shaft_frequency_Hz",
                ],
            ),
            "diagnostic": float(
                self._config["diagnostic_scores"].get(
                    diagnostic_status.value,
                    self._config["diagnostic_scores"]["WARNING"],
                )
            ),
            "availability": (
                float(self._config["missing_sensor_score"])
                if sensor_error_count
                else 100.0
            ),
        }
        weights = self._config["component_weights"]
        weighted_total = 0.0
        included_weight = 0.0
        for name, score in components.items():
            if score is None:
                continue
            weight = float(weights[name])
            weighted_total += score * weight
            included_weight += weight
        if included_weight == 0:
            return None
        return round(max(0.0, min(100.0, weighted_total / included_weight)), 1)
