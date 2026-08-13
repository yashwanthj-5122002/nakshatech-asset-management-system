"""Shared pytest bootstrap for backend tests.

The backend test suite imports modules from the top-level ``app`` package.
When pytest is invoked through its console entry point inside the Docker
container, the repository backend root is not guaranteed to be present on
``sys.path`` during test-module collection. Add it once here before pytest
imports individual test modules so every backend test runs consistently via
both ``pytest`` and ``python -m pytest``.
"""

from __future__ import annotations

from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
