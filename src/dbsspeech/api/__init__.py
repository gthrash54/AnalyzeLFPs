"""HTTP surface. Thin: it validates and delegates, never reimplements."""

from __future__ import annotations

from .main import app, serve

__all__ = ["app", "serve"]
