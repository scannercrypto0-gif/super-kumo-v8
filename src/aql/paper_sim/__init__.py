"""Strictly offline assumed execution. No broker, routing or promotion authority."""
from .engine import PaperSimulator

__all__ = ["PaperSimulator"]
