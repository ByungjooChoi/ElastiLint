#!/usr/bin/env python3
"""
ElastiLint uninstaller.

Removes everything install.py created: the ElastiLint agent, the two validation
tools, the dsl-scratch index, and the three workflows. Reads KIBANA_URL and
KIBANA_API_KEY the same way install.py does (from .env or the environment).

Usage:
    python3 scripts/uninstall.py      # on Windows: python scripts\\uninstall.py
"""
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

AGENT_ID = "elastilint"
# Includes legacy v1 names (validate-querydsl, create-dsl-scratch) so uninstall also
# cleans up clusters that were set up with an earlier version.
TOOL_IDS = ["validate-esql", "validate-search", "validate-querydsl"]
WORKFLOW_NAMES = [
    "validate-esql", "validate-search", "validate-querydsl",
    "create-dsl-scratch", "create-schema-scratch",
]

TEARDOWN_INDEX_YAML = """name: elastilint-teardown
enabled: true
triggers:
  - type: manual
steps:
  - name: drop_scratch
    type: elasticsearch.request
    with:
      method: DELETE
      path: /dsl-scratch
    on-failure:
      continue: true
  - name: drop_schema_scratch
    type: elasticsearch.request
    with:
      method: DELETE
      path: /elastilint-schema-scratch
    on-failure:
      continue: true
"""


def load_config():
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
        sys.exit("ERROR: KIBANA_URL and KIBANA_API_KEY are required (see .env.example).")
    return url, api_key


def api(url, api_key, method, path, body=None):
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


def fail(msg):
    sys.exit("ERROR: " + msg)


def check_auth(status, what):
    """Abort on auth failures so we never report a clean removal that did not
    actually happen. (404s are fine here -- the resource is simply already gone.)"""
    if status in (401, 403):
        fail(
            "authentication/authorization failed while trying to %s (HTTP %s).\n"
            "       Check KIBANA_API_KEY and its privileges." % (what, status)
        )


def uninstall():
    url, api_key = load_config()
    print("Target Kibana: " + url + "\n")

    # Verify connectivity and credentials up front.
    status, listing = api(url, api_key, "GET", "/api/workflows")
    check_auth(status, "reach the Kibana Workflows API")
    if not (200 <= status < 300):
        fail("could not reach the Kibana Workflows API (HTTP %s): %s" % (status, listing))

    # 1) Drop the dsl-scratch index (server-side, before workflows are removed).
    status, resp = api(url, api_key, "POST", "/api/workflows/test",
                       {"inputs": {}, "workflowYaml": TEARDOWN_INDEX_YAML})
    check_auth(status, "drop the dsl-scratch index")
    print("  dsl-scratch teardown triggered: HTTP %s" % status)

    # 2) Agent.
    status, _ = api(url, api_key, "DELETE", "/api/agent_builder/agents/" + AGENT_ID)
    check_auth(status, "delete the agent")
    print("  agent %s: HTTP %s" % (AGENT_ID, status))

    # 3) Tools.
    for tid in TOOL_IDS:
        status, _ = api(url, api_key, "DELETE", "/api/agent_builder/tools/" + tid)
        check_auth(status, "delete tool '%s'" % tid)
        print("  tool %s: HTTP %s" % (tid, status))

    # 4) Workflows (resolve names -> ids, then bulk delete).
    status, listing2 = api(url, api_key, "GET", "/api/workflows")
    check_auth(status, "list workflows")
    ids = [w["id"] for w in (listing2.get("results") or []) if w.get("name") in WORKFLOW_NAMES]
    if ids:
        status, _ = api(url, api_key, "DELETE", "/api/workflows", {"ids": ids})
        check_auth(status, "delete workflows")
        print("  workflows deleted (%s): HTTP %s" % (", ".join(ids), status))
    else:
        print("  no matching workflows found")

    print("\nElastiLint removed.")


if __name__ == "__main__":
    try:
        uninstall()
    except urllib.error.URLError as e:
        sys.exit("ERROR: could not reach KIBANA_URL (%s). Check the URL and your network." % e.reason)
