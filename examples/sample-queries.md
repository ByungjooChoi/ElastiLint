# Sample queries

Paste these into the **ElastiLint** agent (Kibana → Agents → ElastiLint) to see it
in action. No setup data is required — the default validation is index-independent.

## ES|QL

**Valid**
```esql
FROM my-index | WHERE status == 200 | STATS count = COUNT(*) BY host | SORT count DESC | LIMIT 10
```

**Invalid — syntax error** (`WHEREE` typo → `parsing_exception`)
```esql
FROM my-index | WHEREE status == 200
```

**Invalid — wrong operator** (`=` instead of `==`)
```esql
FROM my-index | WHERE status = 200
```

**Invalid — incomplete expression**
```esql
FROM my-index | EVAL x = | LIMIT 5
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
fields/types against a real mapping, just ask the agent:

> Validate this against the `kibana_sample_data_logs` index: `{ "query": { "range": { "@timestamp": { "gte": "now-1h" } } } }`
