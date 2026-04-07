import time
from typing import Optional
from dataclasses import dataclass

@dataclass
class Regression:
    type:         str
    severity:     str          
    message:      str
    metric:       float
    baseline:     float
    delta:        float
    action:       str          

class RegressionDetector:

    THRESHOLDS = {
        "min_quality":      7.0,    
        "quality_drop":     0.5,    
        "max_error_rate":   0.03,   
        "error_spike":      2.0,    
        "max_latency_ms":   5000,
        "latency_spike":    2.0,    
        "cost_spike":       2.0,    
    }

    async def check_all(
        self,
        recent_metrics:   dict,
        baseline_metrics: dict
    ) -> list[Regression]:
        regressions = []

        if recent_metrics["avg_score"] < self.THRESHOLDS["min_quality"]:
            regressions.append(Regression(
                type     = "quality_below_minimum",
                severity = "high",
                message  = f"Average quality {recent_metrics['avg_score']:.2f} "
                           f"below minimum {self.THRESHOLDS['min_quality']}",
                metric   = recent_metrics["avg_score"],
                baseline = self.THRESHOLDS["min_quality"],
                delta    = recent_metrics["avg_score"] - self.THRESHOLDS["min_quality"],
                action   = "Review recent prompt or model changes. "
                           "Pull worst-scoring examples and diagnose."
            ))

        if baseline_metrics.get("avg_score", 0) > 0:
            drop = baseline_metrics["avg_score"] - recent_metrics["avg_score"]
            if drop > self.THRESHOLDS["quality_drop"]:
                regressions.append(Regression(
                    type     = "quality_regression",
                    severity = "high" if drop > 1.0 else "medium",
                    message  = f"Quality dropped {drop:.2f} points "
                               f"({baseline_metrics['avg_score']:.2f} → {recent_metrics['avg_score']:.2f})",
                    metric   = recent_metrics["avg_score"],
                    baseline = baseline_metrics["avg_score"],
                    delta    = -drop,
                    action   = "Compare current prompt vs last-known-good. "
                               "Check if model was updated."
                ))

        if recent_metrics.get("error_rate", 0) > self.THRESHOLDS["max_error_rate"]:
            regressions.append(Regression(
                type     = "error_spike",
                severity = "critical",
                message  = f"Error rate {recent_metrics['error_rate']:.1%} "
                           f"above threshold {self.THRESHOLDS['max_error_rate']:.0%}",
                metric   = recent_metrics["error_rate"],
                baseline = self.THRESHOLDS["max_error_rate"],
                delta    = recent_metrics["error_rate"] - self.THRESHOLDS["max_error_rate"],
                action   = "Check Anthropic API status. Review error logs immediately."
            ))

        if (baseline_metrics.get("avg_latency_ms", 0) > 0 and
            recent_metrics.get("avg_latency_ms", 0) >
            baseline_metrics["avg_latency_ms"] * self.THRESHOLDS["latency_spike"]):
            regressions.append(Regression(
                type     = "latency_regression",
                severity = "medium",
                message  = f"Latency {recent_metrics['avg_latency_ms']:.0f}ms "
                           f"is {recent_metrics['avg_latency_ms'] / baseline_metrics['avg_latency_ms']:.1f}x "
                           f"baseline ({baseline_metrics['avg_latency_ms']:.0f}ms)",
                metric   = recent_metrics["avg_latency_ms"],
                baseline = baseline_metrics["avg_latency_ms"],
                delta    = recent_metrics["avg_latency_ms"] - baseline_metrics["avg_latency_ms"],
                action   = "Check if model changed. Review parallel vs sequential tool calls."
            ))

        return regressions