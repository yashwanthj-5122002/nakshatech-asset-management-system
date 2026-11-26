"""Offline production configuration checks. Never connects to a server."""
import json
import re
from pathlib import Path
import yaml

root = Path(__file__).resolve().parents[1]
for path in [root / ".cpanel.yml", *root.glob(".github/workflows/*.yml")]:
    yaml.safe_load(path.read_text())
compose = yaml.safe_load((root / "docker-compose.production.yml").read_text())
assert set(compose["services"]) == {"db", "redis", "minio", "backend", "frontend", "nginx"}
for name, service in compose["services"].items():
    assert "healthcheck" in service
    assert "restart" not in service or service["restart"] == "unless-stopped"
    if name != "nginx":
        assert "ports" not in service
assert compose["services"]["nginx"]["ports"][0].startswith("127.0.0.1:")
assert compose["networks"]["private"]["internal"]
for path in root.glob("scripts/*production*.sh"):
    assert b"\r" not in path.read_bytes(), f"CRLF in {path}"
source = (root / "backend/app/main.py").read_text()
compile(source, "main.py", "exec")
template = (root / ".env.production.example").read_text()
keys = {line.split("=", 1)[0] for line in template.splitlines() if "=" in line and not line.startswith("#")}
required = set(re.findall(r"\$\{([A-Z_]+)", (root / "docker-compose.production.yml").read_text()))
assert required - keys == {"PRODUCTION_ENV_FILE", "RELEASE_SHA"}
package = json.loads((root / "frontend/package.json").read_text())
quality = (root / ".github/workflows/quality.yml").read_text()
for name in re.findall(r"npm run ([\w:-]+)", quality):
    assert name in package["scripts"], name
assert "continue-on-error" not in quality
print("Production YAML, networking, LF, Python syntax, environment and npm command checks passed")
