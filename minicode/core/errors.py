"""Stable package-level exceptions."""


class MiniCodeError(Exception):
    """Base exception for errors intended to cross subsystem boundaries."""


__all__ = ["MiniCodeError"]
