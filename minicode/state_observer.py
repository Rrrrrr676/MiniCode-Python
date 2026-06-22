"""Compatibility facade for minicode.control.state_observer."""

import sys as _sys
from minicode.control import state_observer as _implementation

_implementation.__all__ = ["KalmanFilter","MeasurementVector","ObservedState","StateObserver"]
_sys.modules[__name__] = _implementation

from minicode.control.state_observer import (
    KalmanFilter,
    MeasurementVector,
    ObservedState,
    StateObserver,
)

__all__ = [
    "KalmanFilter",
    "MeasurementVector",
    "ObservedState",
    "StateObserver",
]
