"""cPanel/Passenger entry point for the NakshaTech FastAPI backend.

This version makes the application root deterministic, loads the private
production .env file before importing the application, and writes startup
tracebacks to tmp/passenger_startup_error.log.
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent
TMP_ROOT = APP_ROOT / "tmp"
ENV_FILE = APP_ROOT / ".env"

if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

# Passenger may start with a working directory other than the application root.
# Pydantic resolves env_file=".env" relative to the current working directory,
# so make the root explicit before importing app.core.config.
os.chdir(APP_ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=ENV_FILE, override=False)
except Exception:
    # pydantic-settings will still read .env after os.chdir(APP_ROOT).
    pass

# Safe mount defaults. Values explicitly present in .env remain authoritative.
os.environ.setdefault("ENVIRONMENT", "production")
os.environ.setdefault("API_PREFIX", "")
os.environ.setdefault("ROOT_PATH", "/api")
os.environ.setdefault("ENABLE_BACKGROUND_WATCHER", "false")

try:
    from app.main import app, initialize_application
    from cpanel_wsgi_adapter import ASGItoWSGI

    initialize_application()
    application = ASGItoWSGI(app)
except Exception:
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    (TMP_ROOT / "passenger_startup_error.log").write_text(
        traceback.format_exc(),
        encoding="utf-8",
    )
    raise
