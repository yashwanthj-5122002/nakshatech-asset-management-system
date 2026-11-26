"""Read-only checks of the local deployment; never print credentials or records."""
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
results = []


def check(base, path, expected=200, token=None, payload=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(base + path, headers=headers,
                      data=json.dumps(payload).encode() if payload else None)
    body = b""
    try:
        with urlopen(request, timeout=30) as response:
            status, body = response.status, response.read()
    except HTTPError as error:
        status = error.code
    except OSError:
        status = "connection-error"
    results.append({"url": base + path, "status": status,
                    "expected": expected, "passed": status == expected})
    print(f"{'PASS' if status == expected else 'FAIL'} {base}{path}: {status}", flush=True)
    try:
        return json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None


for base in ("http://localhost:3100", "http://localhost:8088"):
    check(base, "/")
    check(base, "/api/health")
    check(base, "/assets")
    check(base, "/api/assets", expected=401)

base = "http://localhost:8100"
check(base, "/api/health")
check(base, "/api/assets", expected=401)
check(base, "/api/assets", expected=401, token="invalid-qa-token")

env = {}
for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
    key, sep, value = line.partition("=")
    if sep and not key.lstrip().startswith("#"):
        env[key.strip()] = value.strip().strip('"\'')
if env.get("SEED_ADMIN_EMAIL") and env.get("SEED_ADMIN_PASSWORD"):
    auth = check(base, "/api/auth/login", payload={
        "email": env["SEED_ADMIN_EMAIL"], "password": env["SEED_ADMIN_PASSWORD"]})
    token = (auth or {}).get("access_token")
    if token:
        for path in ("/api/dashboard/summary", "/api/dashboard/it",
                     "/api/assets?limit=5", "/api/it-activity/handover-records?limit=5",
                     "/api/it-activity/custody-employees?search=qa&limit=5",
                     "/api/notifications/global/unread-count"):
            check(base, path, token=token)
        check(base, "/api/management/project-tracking-sales/access", expected=403, token=token)
    else:
        print("Authenticated checks unavailable: existing seed credentials did not yield a token.")

(ROOT / "artifacts/qa/live-smoke-results.json").write_text(
    json.dumps(results, indent=2), encoding="utf-8")
raise SystemExit(0 if all(row["passed"] for row in results) else 1)
