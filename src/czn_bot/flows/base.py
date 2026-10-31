"""
Base Flow interface and Action definitions.
Pure logic: Flows return Actions instead of directly calling ADB.
Enables headless, deterministic testing on static screenshots without BlueStacks.
"""
from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import numpy as np

from czn_bot.states import State


class ActionType(Enum):
    NONE = "NONE"       # Passive waiting or observation
    TAP = "TAP"         # Tap at (x, y)
    SWIPE = "SWIPE"     # Swipe from (x1, y1) to (x2, y2)
    BACK = "BACK"       # Android keyevent BACK (4)
    WAIT = "WAIT"       # Pause for duration seconds
    STOP = "STOP"       # Halt the runner


@dataclass
class Action:
    type: ActionType
    x: Optional[int] = None
    y: Optional[int] = None
    x2: Optional[int] = None
    y2: Optional[int] = None
    duration: float = 0.0
    name: str = ""
    random_offset: bool = True
    reason: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def tap(cls, x: int, y: int, name: str = "", random_offset: bool = True, extra: Optional[Dict[str, Any]] = None, **kwargs) -> "Action":
        merged = dict(kwargs)
        if extra and isinstance(extra, dict):
            merged.update(extra)
        return cls(ActionType.TAP, x=int(x), y=int(y), name=name, random_offset=random_offset, extra=merged)

    @classmethod
    def swipe(cls, x1: int, y1: int, x2: int, y2: int, duration: float = 0.4, name: str = "", extra: Optional[Dict[str, Any]] = None, **kwargs) -> "Action":
        merged = dict(kwargs)
        if extra and isinstance(extra, dict):
            merged.update(extra)
        return cls(ActionType.SWIPE, x=int(x1), y=int(y1), x2=int(x2), y2=int(y2), duration=duration, name=name, extra=merged)

    @classmethod
    def back(cls, name: str = "Back", extra: Optional[Dict[str, Any]] = None, **kwargs) -> "Action":
        merged = dict(kwargs)
        if extra and isinstance(extra, dict):
            merged.update(extra)
        return cls(ActionType.BACK, name=name, extra=merged)

    @classmethod
    def wait(cls, seconds: float = 1.0, name: str = "Wait", extra: Optional[Dict[str, Any]] = None, **kwargs) -> "Action":
        merged = dict(kwargs)
        if extra and isinstance(extra, dict):
            merged.update(extra)
        return cls(ActionType.WAIT, duration=seconds, name=name, extra=merged)

    @classmethod
    def none(cls, name: str = "Idle", extra: Optional[Dict[str, Any]] = None, **kwargs) -> "Action":
        merged = dict(kwargs)
        if extra and isinstance(extra, dict):
            merged.update(extra)
        return cls(ActionType.NONE, name=name, extra=merged)

    @classmethod
    def stop(cls, reason: str = "", extra: Optional[Dict[str, Any]] = None, **kwargs) -> "Action":
        merged = dict(kwargs)
        if extra and isinstance(extra, dict):
            merged.update(extra)
        return cls(ActionType.STOP, reason=reason, extra=merged)


class Flow(ABC):
    """
    Abstract Base Class for Bot operational flows.
    A flow is responsible only for evaluating (State, details, screen) -> Action.
    The runner handles the loop, screen captures, confirm frames, ADB execution, and watchdogs.
    """

    def __init__(self, **kwargs):
        self.context: Dict[str, Any] = {}

    @abstractmethod
    def handle(self, state: State, details: Dict[str, Any], screen: Optional[np.ndarray]) -> Action:
        """Evaluate the confirmed state and return the next Action to execute."""
        pass
