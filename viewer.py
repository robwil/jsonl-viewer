#!/usr/bin/env python3
"""Thin shim for backward compatibility — delegates to viewer package."""

from viewer.__main__ import main_cli
from viewer.parser import _is_gpg_file, parse_chat  # noqa: F401 — used by tests

if __name__ == "__main__":
    main_cli()
