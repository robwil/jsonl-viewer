"""SillyTavern JSONL chat viewer package."""

# Re-export for backward compatibility (used by tests)
from .parser import _is_gpg_file, parse_chat

__all__ = ["parse_chat", "_is_gpg_file"]
