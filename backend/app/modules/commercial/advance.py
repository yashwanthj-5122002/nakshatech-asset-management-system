"""Stable commercial-layer import path for isolated client-advance models.

The Phase 1 implementation was started under the Finance module because the ledger is
Finance-owned. Re-export it here so commercial integrations can use the approved
``app.modules.commercial.advance`` namespace without duplicating tables or metadata.
"""

from app.modules.finance.advance import *  # noqa: F403
from app.modules.finance.advance import __all__
