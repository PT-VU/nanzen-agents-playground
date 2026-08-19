"""Shared tool base for runtime and tool-only tests."""

from __future__ import annotations

try:
    from smolagents import Tool
except ModuleNotFoundError:

    class Tool:  # type: ignore[no-redef]
        """Minimal fallback so deterministic tool tests do not require smolagents."""

        name: str
        description: str
        inputs: dict
        output_type: str
