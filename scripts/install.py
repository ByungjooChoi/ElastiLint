#!/usr/bin/env python3
"""
ElastiLint installer.

Deploys the ElastiLint query validator (workflows, tools, and agent) to an
Elastic Serverless project via the Kibana Agent Builder and Workflows APIs.

- No third-party dependencies (Python 3.8+ standard library only).
- Cross-platform: macOS, Linux, Windows.
- Reads KIBANA_URL and KIBANA_API_KEY from a local .env file (or real
  environment variables). The .env file is gitignored and supplied by whoever
  runs the install -- no credentials are stored in this repository.

Usage:
    cp .env.example .env      # then edit .env and fill in your values
    python3 scripts/install.py
"""
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFS = ROOT / "definitions"


def load_config():
    """Load KIBANA_URL and KIBANA_API_KEY from .env (if present) or the env."""
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))
    url = os.environ.get("KIBANA_URL", "").rstrip("/")
    api_key = os.environ.get("KIBANA_API_KEY", "")
    if not url or not api_key:
        sys.exit(
            "ERROR: KIBANA_URL and KIBANA_API_KEY are required.\n"
            "       Copy .env.example to .env and fill in your values, or set\n"
            "       them as environment variables."
        )
    return url, api_key


def api(url, api_key, method, path, body=None):
    """Make a Kibana API call. Returns (status_code, parsed_body)."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url + path, data=data, method=method)
    req.add_header("Authorization", "ApiKey " + api_key)
    req.add_header("kbn-xsrf", "true")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            text = resp.read().decode("utf-8")
            return resp.status, (json.loads(text) if text else {})
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8")
        try:
            return e.code, json.loads(text)
        except ValueError:
            return e.code, text


def workflow_name(yaml_text):
    for line in yaml_text.splitlines():
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip()
    return None


def install():
    url, api_key = load_config()
    print("Target Kibana: " + url + "\n")

    # 1) Workflows -- create only those not already present (matched by name).
    _, listing = api(url, api_key, "GET", "/api/workflows")
    existing = {w.get("name") for w in (listing.get("results") or [])}
    wf_dir = DEFS / "workflows"
    pending = []
    for f in sorted(wf_dir.glob("*.yaml")):
        text = f.read_text(encoding="utf-8")
        name = workflow_name(text) or f.stem
        if name in existing:
            print("  workflow '%s' already exists -- skipping" % name)
        else:
            pending.append((name, text))
    if pending:
        status, resp = api(
            url, api_key, "POST", "/api/workflows",
            {"workflows": [{"yaml": text} for _, text in pending]},
        )
        for w in (resp.get("created") or []):
            print("  workflow created: %s (valid=%s)" % (w.get("id"), w.get("valid")))
        for w in (resp.get("failed") or []):
            print("  workflow FAILED: %s" % w)

    # 2) Create the dsl-scratch index by running the setup workflow server-side.
    setup_yaml = (wf_dir / "create-dsl-scratch.yaml").read_text(encoding="utf-8")
    status, resp = api(url, api_key, "POST", "/api/workflows/test",
                       {"inputs": {}, "workflowYaml": setup_yaml})
    if status < 300:
        print("  dsl-scratch index setup triggered (exec %s)" % resp.get("workflowExecutionId", "?"))
    else:
        print("  WARNING: dsl-scratch setup returned %s: %s" % (status, resp))

    # 3) Tools -- upsert (create; if it exists, delete then recreate).
    for f in sorted((DEFS / "tools").glob("*.json")):
        tool = json.loads(f.read_text(encoding="utf-8"))
        status, resp = api(url, api_key, "POST", "/api/agent_builder/tools", tool)
        if status >= 300:
            api(url, api_key, "DELETE", "/api/agent_builder/tools/" + tool["id"])
            status, resp = api(url, api_key, "POST", "/api/agent_builder/tools", tool)
        print("  tool %s: HTTP %s" % (tool["id"], status))

    # 4) Agent -- upsert.
    agent = json.loads((DEFS / "agent" / "elastilint.json").read_text(encoding="utf-8"))
    status, resp = api(url, api_key, "POST", "/api/agent_builder/agents", agent)
    if status >= 300:
        api(url, api_key, "DELETE", "/api/agent_builder/agents/" + agent["id"])
        status, resp = api(url, api_key, "POST", "/api/agent_builder/agents", agent)
    print("  agent %s: HTTP %s" % (agent["id"], status))

    print(
        "\nDone. Open Kibana -> Agents -> ElastiLint and paste an ES|QL or "
        "Query DSL query to validate it."
    )


if __name__ == "__main__":
    install()
