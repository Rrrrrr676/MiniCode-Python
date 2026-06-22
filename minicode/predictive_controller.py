"""Compatibility facade for minicode.control.predictive."""

import sys as _sys
from minicode.control import predictive as _implementation

_implementation.__all__ = ["ExponentialSmoother","MovingAveragePredictor","PredictionHorizon","PredictionResult","PredictiveAction","PredictiveController"]
_sys.modules[__name__] = _implementation

from minicode.control.predictive import (
    ExponentialSmoother,
    MovingAveragePredictor,
    PredictionHorizon,
    PredictionResult,
    PredictiveAction,
    PredictiveController,
)

__all__ = [
    "ExponentialSmoother",
    "MovingAveragePredictor",
    "PredictionHorizon",
    "PredictionResult",
    "PredictiveAction",
    "PredictiveController",
]
