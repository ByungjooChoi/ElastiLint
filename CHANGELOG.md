# Changelog

All notable changes to ElastiLint are documented here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased] — v2 (in progress)

### Added
- **`validate-search`** — validates a full search body (Query DSL, `retriever`/`rrf`/`text_similarity_reranker`, `knn`, `aggs`, `semantic`) via the `_search` API against a zero-doc scratch index. Catches retriever-envelope errors (e.g. `_index` inside `standard`), top-level cramming (unknown keys such as an `Authorization` key in the body), and any construct the cluster rejects.
- **`elastilint-schema-scratch`** index — zero-document index with an ELSER-backed `semantic_text` field, so a `semantic` query against a non-`semantic_text` field is caught.
- **`validate-request`** — validates a full HTTP request (method + path + body): catches wrong method (`PUT` vs `POST` → "Incorrect HTTP method") and bad endpoints ("no handler found"). Index writes are redirected to the `elastilint-write-scratch` index so real data is untouched; `_security/api_key` requests are validated by setting a 60s expiration (a malformed role_descriptor / DLS is rejected); destructive/heavy requests are warned about, not executed.

### Changed
- Query DSL validation moved from `_validate/query` to `_search` (`_validate/query` could not handle `semantic`, `retriever`, or top-level body keys).
- The agent routes **all** Query DSL / search bodies to `validate-search` (removes the `validate-querydsl` vs `validate-search` routing ambiguity).
- Reranker syntax is validated **without running the rerank** (error-type interpretation: parse error = invalid; `size`/inference error = syntax OK).
- **License: MIT → Apache-2.0.**
- Supported Elastic versions documented in line with Elastic's EOL policy; semantic validation uses built-in ELSER (Serverless / Stack 9.x+ with Agent Builder).

### Removed
- **`validate-querydsl`** tool/workflow — superseded by `validate-search`.

## [0.1.0] — initial
- ES|QL + Query DSL validation via Agent Builder workflow tools, `dsl-scratch` index, cross-platform `install.py` / `uninstall.py` (fail-fast, dynamic workflow-id wiring).
