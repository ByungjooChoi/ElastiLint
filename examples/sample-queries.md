# Sample queries

Paste these into the **ElastiLint** agent (Kibana → Agents → ElastiLint). No sample data is
required — everything validates against the empty scratch indices the installer creates.
✅ = ElastiLint catches it · ❌ = ElastiLint does **not** catch it (and why).

## ES|QL

**✅ Valid**
```esql
FROM dsl-scratch | LIMIT 10
```

**✅ Invalid — syntax error** (`WHEREE` typo → `parsing_exception`)
```esql
FROM dsl-scratch | WHEREE status == 200
```

**✅ Invalid — unknown index** (`no-such-index` does not exist)
```esql
FROM no-such-index | LIMIT 10
```

## Query DSL / search body  → `validate-search`

**✅ Valid**
```json
{ "query": { "bool": {
  "must":   [ { "multi_match": { "query": "travel profile", "fields": ["title^3","content"] } } ],
  "filter": [ { "term": { "_index": "kb_hr_content" } } ]
}}}
```

**✅ Invalid — typo'd clause** (`matchh` → unknown query)
```json
{ "query": { "bool": { "must": [ { "matchh": { "title": "hello" } } ] } } }
```

**✅ Invalid — retriever envelope: `_index` inside `standard`** (the MSG mistake → `x_content_parse_exception: [standard] unknown field [_index]`)
```json
{ "retriever": { "rrf": { "retrievers": [
  { "standard": { "_index": "kb_hr_content",
                  "query": { "multi_match": { "query": "call off", "fields": ["title^3","content"] } } } }
], "rank_window_size": 100, "rank_constant": 20 } } }
```

**✅ Invalid — unsupported key crammed into the body** (`Authorization` is not a search-body key)
```json
{ "Authorization": "ApiKey abc", "query": { "match_all": {} } }
```

**✅ Invalid — `semantic` on a field of the WRONG type** (a `text` field → "does not support semantic queries"; ask the agent to validate against an index whose `title` is `text`)
```json
{ "query": { "semantic": { "field": "title", "query": "travel" } } }
```

**❌ NOT caught — `semantic` on a field that does NOT exist** (typo'd field name passes silently)
```json
{ "query": { "semantic": { "field": "semantic_txt", "query": "travel" } } }
```
> Elasticsearch only errors when the field *exists* but is the wrong type. To check a field
> *name* (e.g. `semantic_text` vs `semantic_content`), ask: *"check this against the
> `kb_enterprise_content` index"* — the agent reads the mapping with `get_index_mapping`.

## Full request  → `validate-request`

**✅ Invalid — wrong HTTP method** (`_search` needs `GET`/`POST` → "Incorrect HTTP method")
```
PUT kb_all/_search
{ "query": { "match_all": {} } }
```

**✅ Invalid — bad endpoint** (`_serch` typo → "no handler found")
```
POST kb_all/_serch
{ "query": { "match_all": {} } }
```

**✅ Valid write — structure checked safely** (the agent redirects the write to a throwaway index, so your real data is untouched)
```
PUT kb_hr_content/_doc/1
{ "title": "Call-Off Procedure", "content": "..." }
```

**✅ Invalid `_security/api_key`** (an `indices` entry missing `names`/`privileges` → rejected). The agent adds `"expiration": "60s"` so any key it creates self-expires.
```
POST _security/api_key
{ "name": "kb-search-as-amisha",
  "role_descriptors": { "dls": { "indices": [ { "query": { "match_all": {} } } ] } } }
```

## Not caught — and why (be honest in the demo)

- **`semantic` on a typo'd / non-existent field name** — passes silently (see above).
- **`Authorization: ApiKey ...` header pasted in Dev Tools** — that header doesn't work in Kibana
  Dev Tools, but it's a client-tooling fact the cluster can't judge. The agent flags it as a
  `[heuristic]` heads-up, separate from the VALID/INVALID verdict.
- **Whether DLS returns the right documents** for a persona — needs real data + persona testing.
- **Search relevance / ranking quality** — a structurally valid query that ranks poorly is still valid.

## Validate against a real index

By default validation is index-independent (structure only). To also check field names and types,
ask the agent in plain language:

> Validate this against the `kibana_sample_data_logs` index: `{ "query": { "range": { "@timestamp": { "gte": "now-1h" } } } }`
