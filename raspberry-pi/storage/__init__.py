"""Local durable state used for transition-based fault history."""

from .event_history import FaultEventTracker

__all__ = ["FaultEventTracker"]
