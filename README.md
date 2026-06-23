# ElastiLint

**A query linter for Elasticsearch, built on Elastic Agent Builder.**

Paste an **ES|QL** query, a **Query DSL / search body**, or a **full request** into the
ElastiLint agent and it tells you whether it is valid — validated **by the cluster itself**,
not guessed by an LLM — then explains any error in plain language and proposes a fix.

> ElastiLint is not a standalone app. It is a small **pack of definitions**
> (workflows + tools + an agent) that you deploy into your own Elastic Serverless
> project. Think of it as config-as-code for Agent Builder.

---

## How it works

The guiding principle is **"the cluster judges, the LLM routes and explains."** The
agent never decides validity from its own knowledge — it sends what you paste to a real
Elasticsearch endpoint and reports what comes back.

| You paste | Validated via | Notes |
|---|---|---|
| **ES\|QL** | `POST /_query` (with `LIMIT 0`) | `parsing_exception` = syntax error; `verification_exception` = unknown index/column. |
| **Query DSL / search body** (`query`, `bool`, `retriever`/`rrf`/reranker, `knn`, `aggs`, `semantic`, …) | `POST /<scratch>/_search` (`validate-search`) | The cluster parses the **whole body** and rejects anything it doesn't support — including retriever-envelope errors and unknown top-level keys. |
| **A full request** (a snippet starting with a method+path line, e.g. `POST kb_all/_search` or `PUT my-index/_doc/1`) | `validate-request` runs the method + path + body | Catches a wrong HTTP method (`Incorrect HTTP method`) and a bad endpoint (`no handler found`). Writes are redirected to a throwaway index; `_security/api_key` gets a 60s expiry so its `role_descriptor` / DLS structure is validated. |

Validation runs against empty **scratch indices** that the installer creates, so structure
and syntax are checked **index-independently** — no setup data required. For checks that
depend on a real mapping (field types, or whether a `semantic` field name actually maps to a
`semantic_text` field), ask the agent to validate against one of your real indices.

## Scope — what it does and doesn't validate

**Caught (by the cluster, no real data needed):**

- ES|QL syntax errors; unknown index/column (when the index exists).
- Query DSL structure: typo'd clauses (`matchh`), malformed clause structure, unknown query types.
- Retriever / search-body envelope: `rrf` and `text_similarity_reranker` structure, `_index`
  placed inside a `standard` retriever, and unknown top-level keys (e.g. an `Authorization`
  key crammed into the body).
- A `semantic` query aimed at an **existing field of the wrong type** (e.g. a `text` field).
- Wrong HTTP method (`PUT` where `POST`/`GET` is required) and bad endpoints/paths.
- `_security/api_key` request structure (malformed `role_descriptor` / DLS), via a 60s
  self-expiring key.

**Not caught — and why:**

- **A `semantic` query on a field that does not exist** (a typo'd field name) passes silently —
  Elasticsearch only errors when the field exists but is the wrong type. To check a field
  *name*, use the "validate against my real index" path (the agent reads the mapping).
- **Field types / mappings in general** — only checked against a real index you name.
- **Whether DLS actually isolates the right documents** — needs real data and per-persona
  testing, not structure validation.
- **The HTTP envelope beyond method/path** — e.g. an `Authorization: ApiKey` header pasted in
  Kibana Dev Tools style won't work in Dev Tools, but that's a client-tooling fact the cluster
  can't judge; the agent flags it as a `[heuristic]` heads-up, separate from the cluster verdict.
- **Search relevance / quality** — a structurally valid query that simply ranks poorly is still
  "valid."

---

## Prerequisites

- **Elastic Serverless**, or a self-managed / ECH **Stack** release with **Agent Builder**
  and **Workflows** enabled (built and tested against 8.19 and 9.4; see Compatibility below).
- An **Elastic API key** with privileges to manage Agent Builder tools/agents and
  Workflows.
- **Python 3.8+** (standard library only — no `pip install` needed).

## Compatibility & supported versions

Built and tested against **Elastic 8.19** and **9.4**, and expected to work on other releases that
provide **Agent Builder**, **Workflows**, and (for semantic validation) the built-in **ELSER**
endpoint (`.elser-2-elasticsearch`) — available on **Elastic Serverless** and recent self-managed /
ECH **Stack** releases.

Because ElastiLint delegates every verdict to the cluster — it runs your query against the cluster's
own `_search` / `_query` APIs — it **automatically tracks whatever your cluster's version supports**.
There is no version-specific validation logic to maintain: a construct that is valid on 9.4 but not
on 8.19 is judged correctly by each cluster.

Run a release that is still within Elastic's support window; versions past **End of Life (EOL)** are
not supported. See [Elastic Product End of Life Dates](https://www.elastic.co/support/eol).

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

The installer creates the workflows, the scratch indices (`dsl-scratch`,
`elastilint-schema-scratch`, `elastilint-write-scratch`), the tools, and the ElastiLint
agent. If the API key is missing or lacks privileges it **fails loudly** (non-zero exit)
instead of printing "Done".

Re-running is safe: the tools and agent are refreshed in place, and existing
workflows are left untouched. To apply a change you made to a workflow's YAML, run
`uninstall.py` first, then `install.py`.

### Use it

In Kibana, open **Agents** (the Agent Builder chat — it's in the left navigation;
depending on your version/deployment it may sit under a *Build* or *AI* group).
Select **ElastiLint**, then paste an ES|QL query, a Query DSL / search body, or a full request.

To validate against a real index's mapping (not just structure), ask in plain
language, e.g. *"Validate this Query DSL against the `my-app-logs` index: { … }"*.
More examples are in [`examples/sample-queries.md`](examples/sample-queries.md).

### Uninstall

```bash
python3 scripts/uninstall.py
```

Removes the agent, the tools, the scratch indices, and the workflows.

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
├── CHANGELOG.md
├── .env.example                 # template; copy to .env (gitignored)
├── .gitignore
├── LICENSE
├── NOTICE
├── definitions/
│   ├── workflows/               # Elastic Workflows (YAML)
│   │   ├── create-dsl-scratch.yaml
│   │   ├── create-schema-scratch.yaml
│   │   ├── create-write-scratch.yaml
│   │   ├── validate-esql.yaml
│   │   ├── validate-search.yaml
│   │   └── validate-request.yaml
│   ├── tools/                   # Agent Builder tools (workflow type)
│   │   ├── validate-esql.json
│   │   ├── validate-search.json
│   │   └── validate-request.json
│   └── agent/
│       └── elastilint.json      # the ElastiLint agent + instructions
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
- Validation result: execution `completed` = valid; `failed` = invalid, with the
  Elasticsearch error in `error_message`.
- Scratch indices: `dsl-scratch` (empty / mapping-less — universal structure checks),
  `elastilint-schema-scratch` (adds an ELSER `semantic_text` field for `semantic` checks),
  and `elastilint-write-scratch` (redirect target for write requests).

---

## License

Apache-2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
