# ElastiLint

**A query linter for Elasticsearch, built on Elastic Agent Builder.**

Paste an **ES|QL** or **Query DSL** query into the ElastiLint agent and it tells you
whether the query is valid — validated **by the cluster itself**, not guessed by an
LLM — then explains any error in plain language and proposes a fix.

> ElastiLint is not a standalone app. It is a small **pack of definitions**
> (workflows + tools + an agent) that you deploy into your own Elastic Serverless
> project. Think of it as config-as-code for Agent Builder.

---

## How it works

The guiding principle is **"the cluster judges, the LLM routes and explains."**
The agent never decides validity from its own knowledge — it sends the query to the
right Elasticsearch endpoint and reports what comes back.

| Query type | Validated via | Behavior |
|---|---|---|
| **ES\|QL** | `POST /_query` (with `LIMIT 0`, so no data is processed) | Valid → succeeds. Invalid → `parsing_exception` (syntax) or `verification_exception` (unknown index/column). |
| **Query DSL** | `POST /<index>/_validate/query` | Runs against an empty `dsl-scratch` index by default, so it is **index-independent**: unknown fields pass, only structural/syntax errors are caught. Pass a real index name to also check fields/types against its mapping. |

The agent auto-detects the language (pipe syntax vs. JSON), calls the matching tool,
states a clear **VALID / INVALID** verdict, and — when invalid — quotes the
Elasticsearch error, explains it, and suggests a corrected query.

### What it catches / what it doesn't

- **Caught:** all ES|QL syntax errors; unknown indices/columns (when the index
  exists); Query DSL structural errors, typo'd clauses (e.g. `matchh`), malformed
  clause structure.
- **Not caught in default (structure-only) mode:** Query DSL field-type mismatches
  and typo'd field names (unknown fields simply pass), and clauses that are
  intrinsically tied to a mapping (`geo_*`, `nested`, `shape`, custom analyzers).
  These require a real index — pass one explicitly to validate against it.

---

## Prerequisites

- An **Elastic Serverless** project (or Stack 9.x) with **Agent Builder** (GA) and
  **Workflows** enabled.
- An **Elastic API key** with privileges to manage Agent Builder tools/agents and
  Workflows.
- **Python 3.8+** (standard library only — no `pip install` needed).

---

## Install

```bash
git clone https://github.com/ByungjooChoi/ElastiLint.git
cd ElastiLint

cp .env.example .env        # then edit .env and fill in your values
python3 scripts/install.py  # on Windows: python scripts\install.py
```

`.env` holds your two secrets and is **gitignored** — it is never committed:

```ini
KIBANA_URL=https://your-project.kb.us-west-2.aws.elastic.cloud
KIBANA_API_KEY=your_encoded_api_key
```

**Getting these values:**

- `KIBANA_URL` — your project's Kibana endpoint. A trailing slash is fine; the
  script strips it.
- `KIBANA_API_KEY` — create an API key in Kibana under **Stack Management →
  Security → API keys** (or your project's *Create API key* button). It needs
  privileges to manage **Workflows** and **Agent Builder** tools/agents; use the
  least privilege that works. Paste the **encoded** value — a single base64 string.

The installer creates the three workflows, the `dsl-scratch` index, the two tools,
and the ElastiLint agent. If the API key is missing or lacks privileges it **fails
loudly** (non-zero exit) instead of printing "Done".

Re-running is safe: the tools and agent are refreshed in place, and existing
workflows are left untouched. To apply a change you made to a workflow's YAML, run
`uninstall.py` first, then `install.py`.

### Use it

In Kibana, open **Agents** (the Agent Builder chat — it's in the left navigation;
depending on your version/deployment it may sit under a *Build* or *AI* group).
Select **ElastiLint**, then paste an ES|QL or Query DSL query.

To validate against a real index's mapping (not just structure), ask in plain
language, e.g. *"Validate this Query DSL against the `my-app-logs` index: { … }"*.
More examples are in [`examples/sample-queries.md`](examples/sample-queries.md).

### Uninstall

```bash
python3 scripts/uninstall.py
```

Removes the agent, both tools, the `dsl-scratch` index, and the three workflows.

---

## Security

- Credentials live only in `.env`, which is in `.gitignore`. Never commit it.
- The scripts read the API key from `.env`/environment and send it as an
  `Authorization: ApiKey` header. The key is never written to logs or other files.
- Prefer a **least-privilege API key** scoped to the project where ElastiLint runs.

---

## Repository layout

```
ElastiLint/
├── README.md
├── .env.example                 # template; copy to .env (gitignored)
├── .gitignore
├── LICENSE
├── definitions/
│   ├── workflows/               # Elastic Workflows (YAML) — the validators
│   │   ├── create-dsl-scratch.yaml
│   │   ├── validate-esql.yaml
│   │   └── validate-querydsl.yaml
│   ├── tools/                   # Agent Builder tools (workflow type)
│   │   ├── validate-esql.json
│   │   └── validate-querydsl.json
│   └── agent/
│       └── elastilint.json      # the ElastiLint agent + persona/instructions
├── scripts/
│   ├── install.py
│   └── uninstall.py
└── examples/
    └── sample-queries.md
```

To customize the agent's persona or behavior, edit
`definitions/agent/elastilint.json` (the `instructions` field) and re-run the
installer.

---

## Implementation notes (gotchas worth knowing)

- Workflow `inputs` support only scalar types (no `object`). The Query DSL query is
  therefore passed as a **string** and sent with an explicit
  `Content-Type: application/json` header so Elasticsearch parses it as JSON.
- Index names cannot start with `_`, so the scratch index is `dsl-scratch`.
- On Serverless the Kibana Console proxy is disabled, so **all** Elasticsearch calls
  go through the Workflows engine (`elasticsearch.request` steps).
- ES|QL validation result: valid → execution `completed`; invalid → `failed` with
  `error_message`. Query DSL validation result: always `completed`, with
  `output.valid` = true/false.

---

## License

MIT — see [LICENSE](LICENSE).
