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
    python3 scripts/install.py      # on Windows: python scripts\\install.py
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


def fail(msg):
    sys.exit("ERROR: " + msg)


def ensure(status, body, what):
    """Abort with a clear message if an API call did not succeed."""
    if status in (401, 403):
        fail(
            "authentication/authorization failed while trying to %s (HTTP %s).\n"
            "       Check KIBANA_API_KEY and that it has privileges to manage\n"
            "       Workflows and Agent Builder tools/agents." % (what, status)
        )
    if not (200 <= status < 300):
        fail("could not %s (HTTP %s): %s" % (what, status, body))


def workflow_name(yaml_text):
    for line in yaml_text.splitlines():
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip()
    return None


def upsert(url, api_key, collection, obj):
    """POST obj to /api/agent_builder/<collection>; if it already exists,
    delete it and POST again. Authentication failures are not treated as
    'already exists' -- they abort via ensure()."""
    path = "/api/agent_builder/" + collection
    status, resp = api(url, api_key, "POST", path, obj)
    if not (200 <= status < 300) and status not in (401, 403):
        api(url, api_key, "DELETE", path + "/" + obj["id"])
        status, resp = api(url, api_key, "POST", path, obj)
    return status, resp


def install():
    url, api_key = load_config()
    print("Target Kibana: " + url + "\n")

    # Verify connectivity and credentials up front, so a bad API key fails loudly
    # instead of silently printing "Done".
    status, listing = api(url, api_key, "GET", "/api/workflows")
    ensure(status, listing, "reach the Kibana Workflows API")

    # 1) Workflows -- create only those not already present (matched by name).
    #    (Existing workflows are left as-is; to apply edits to a workflow's YAML,
    #    run uninstall.py first, then install.py.)
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
        status, resp = api(url, api_key, "POST", "/api/workflows",
                           {"workflows": [{"yaml": text} for _, text in pending]})
        ensure(status, resp, "create workflows")
        # Invalid workflows come back under 'created' with valid=false (not under
        # 'failed'/'failures'), so check both places.
        for w in (resp.get("created") or []):
            print("  workflow created: %s (valid=%s)" % (w.get("id"), w.get("valid")))
            if not w.get("valid"):
                fail("workflow '%s' was rejected as invalid; check its YAML." % w.get("id"))
        for w in (resp.get("failed") or resp.get("failures") or []):
            fail("workflow could not be created: %s" % w)

    # 2) Create the dsl-scratch index by running the setup workflow server-side.
    setup_yaml = (wf_dir / "create-dsl-scratch.yaml").read_text(encoding="utf-8")
    status, resp = api(url, api_key, "POST", "/api/workflows/test",
                       {"inputs": {}, "workflowYaml": setup_yaml})
    ensure(status, resp, "create the dsl-scratch index")
    print("  dsl-scratch index setup triggered (exec %s)" % resp.get("workflowExecutionId", "?"))

    # Resolve the real workflow ids before wiring tools. On a first install the
    # workflow slug equals its name, but if the workflows were ever deleted and
    # recreated, Elastic suffixes the slug (e.g. validate-esql-1). Looking the id
    # up by name keeps the tool -> workflow wiring correct in every case.
    status, listing2 = api(url, api_key, "GET", "/api/workflows")
    ensure(status, listing2, "list workflows")
    name_to_id = {w.get("name"): w.get("id") for w in (listing2.get("results") or [])}

    # 3) Tools -- upsert, wiring each to the resolved workflow id.
    for f in sorted((DEFS / "tools").glob("*.json")):
        tool = json.loads(f.read_text(encoding="utf-8"))
        wf_ref = tool.get("configuration", {}).get("workflow_id")
        if wf_ref in name_to_id:
            tool["configuration"]["workflow_id"] = name_to_id[wf_ref]
        status, resp = upsert(url, api_key, "tools", tool)
        ensure(status, resp, "create tool '%s'" % tool["id"])
        print("  tool %s -> workflow %s: ok" % (tool["id"], tool["configuration"].get("workflow_id")))

    # 4) Agent -- upsert.
    agent = json.loads((DEFS / "agent" / "elastilint.json").read_text(encoding="utf-8"))
    status, resp = upsert(url, api_key, "agents", agent)
    ensure(status, resp, "create agent '%s'" % agent["id"])
    print("  agent %s: ok" % agent["id"])

    print(
        "\nDone. Open Kibana -> Agents -> ElastiLint and paste an ES|QL or "
        "Query DSL query to validate it."
    )


if __name__ == "__main__":
    try:
        install()
    except urllib.error.URLError as e:
        sys.exit("ERROR: could not reach KIBANA_URL (%s). Check the URL and your network." % e.reason)
