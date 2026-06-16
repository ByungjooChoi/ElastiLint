# Sample queries

Paste these into the **ElastiLint** agent (Kibana → Agents → ElastiLint) to see it
in action. No sample data is required: the DSL examples validate against the empty
`dsl-scratch` index (created by `install.py`), and the ES|QL examples below use that
same index so they work on a brand-new cluster.

> Note: `dsl-scratch` is an **empty** index with no mapping. So a *valid* ES|QL
> example can use `FROM dsl-scratch` but must not reference fields (an unknown
> column would correctly come back as `verification_exception`). To validate ES|QL
> that references real fields, put one of **your own** index names in `FROM`.

## ES|QL

**Valid** (no field references, so it works against the empty scratch index)
```esql
FROM dsl-scratch | LIMIT 10
```

**Invalid — syntax error** (`WHEREE` typo → `parsing_exception`)
```esql
FROM dsl-scratch | WHEREE status == 200
```

**Invalid — incomplete expression** (`EVAL` with nothing after `=`)
```esql
FROM dsl-scratch | EVAL x = | LIMIT 5
```

**Invalid — unknown index** (shows the index check; `no-such-index` does not exist)
```esql
FROM no-such-index | LIMIT 10
```

## Query DSL

**Valid**
```json
{ "query": { "bool": { "must": [ { "match": { "title": "hello world" } } ],
                        "filter": [ { "range": { "price": { "gte": 10 } } } ] } } }
```

**Invalid — typo'd clause** (`matchh` → unknown query)
```json
{ "query": { "bool": { "must": [ { "matchh": { "title": "hello" } } ] } } }
```

**Invalid — malformed structure** (`must` given a string instead of clauses)
```json
{ "query": { "bool": { "must": "oops" } } }
```

## Validating against a real index

By default DSL validation ignores field names (index-independent). To also check
fields/types against a real mapping, just ask the agent in plain language:

> Validate this Query DSL against the `kibana_sample_data_logs` index: `{ "query": { "range": { "@timestamp": { "gte": "now-1h" } } } }`
