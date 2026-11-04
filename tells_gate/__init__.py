"""Tells Gate: deterministic AI-writing tell checker driven by banned.md."""
from .core import Rule, Hit, Report, load_rules, check, DEFAULT_BANNED

__all__ = ["Rule", "Hit", "Report", "load_rules", "check", "DEFAULT_BANNED"]
__version__ = "0.1.0"
