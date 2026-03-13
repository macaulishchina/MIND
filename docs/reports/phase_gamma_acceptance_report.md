# Phase γ Acceptance Report

**Generated at:** 2026-03-13  
**Status:** ✅ PASS

---

## Overview

Phase γ — *Advanced Memory Intelligence* — delivers five major capability areas that build on top of
the Phase α (closed-loop feedback) and Phase β (core quality) foundations:

| Sub-task | Area | Gate status |
|----------|------|-------------|
| γ-1 | PolicyNote / PreferenceNote object types | ✅ PASS |
| γ-2 | Graph-augmented retrieval | ✅ PASS |
| γ-3 | Per-capability model routing | ✅ PASS |
| γ-4 | Structured artifact memory (ArtifactIndex) | ✅ PASS |
| γ-5 | Memory decay & auto-archive | ✅ PASS |

---

## γ-1 — PolicyNote / PreferenceNote Object Types

### What was added

* **`PolicyNote`** — captures a recurring behavioural rule inferred from cross-episode evidence.
  Metadata: `trigger_condition`, `action_pattern`, `evidence_refs`, `confidence`, `applies_to_scope`.
* **`PreferenceNote`** — captures a persistent user preference.
  Metadata: `preference_key`, `preference_value`, `strength`, `evidence_refs`.
* Both types are promoted from multi-episode evidence via `assess_policy_promotion()` and
  `assess_preference_promotion()` in `mind/offline/promotion.py`.
* Promotion threshold is **≥ 3 distinct episodes** — a higher bar than SchemaNote (≥ 2 episodes).
* New offline job kinds: `PROMOTE_POLICY`, `PROMOTE_PREFERENCE`.
* **Workspace slot boost**: when the workspace purpose contains decision-related keywords
  (`"decision"`, `"policy"`, `"strategy"`, …), `PolicyNote` candidates receive a +0.15 score
  boost so they surface prominently in decision-making workspaces.

### Key files changed / added

| File | Change |
|------|--------|
| `mind/kernel/schema.py` | Added `PolicyNote`, `PreferenceNote` to `CORE_OBJECT_TYPES` and `REQUIRED_METADATA_FIELDS`; added validation |
| `mind/offline/promotion.py` | Added `assess_policy_promotion()`, `assess_preference_promotion()` |
| `mind/offline_jobs.py` | Added `PROMOTE_POLICY`, `PROMOTE_PREFERENCE` job kinds + payloads |
| `mind/offline/service.py` | Handlers for new job kinds |
| `mind/workspace/builder.py` | PolicyNote score boost for decision purposes |

---

## γ-2 — Graph-Augmented Retrieval

### What was added

* **`mind/kernel/graph.py`** — new module providing:
  * `build_adjacency_index(store)` — builds a bidirectional adjacency map from all active, non-concealed `LinkEdge` objects in O(n) time.
  * `expand_by_graph(seed_ids, adjacency, hops, max_expand)` — BFS expansion with cycle safety and a hard cap on returned IDs.
* **Access service integration** (`mind/access/service.py`):
  * `FLASH` — 0 hops (latency-sensitive; no expansion).
  * `RECALL` — 1-hop expansion; directly connected objects surfaced.
  * `RECONSTRUCT` / `REFLECTIVE_ACCESS` — 2-hop expansion for richer context.
  * Expanded IDs receive a score slightly below the minimum seed score to avoid displacing high-quality retrieval results.
* **`DISCOVER_LINKS`** offline job — automatically creates proposed `LinkEdge` objects via embedding similarity (cosine ≥ `min_similarity` threshold).
* **`schedule_discover_links()`** method added to `OfflineJobScheduler`.

### Key files changed / added

| File | Change |
|------|--------|
| `mind/kernel/graph.py` | New module |
| `mind/access/service.py` | `_graph_expand()`, `_graph_hops_for_mode()` |
| `mind/offline_jobs.py` | `DISCOVER_LINKS` job kind + `DiscoverLinksJobPayload` |
| `mind/offline/service.py` | `_process_discover_links()` handler |
| `mind/offline/scheduler.py` | `schedule_discover_links()` |

---

## γ-3 — Per-Capability Model Routing

### What was added

* **`CapabilityRoutingConfig`** (`mind/capabilities/contracts.py`) — a new Pydantic model that maps
  individual `CapabilityName` values to specific `CapabilityProviderConfig` instances.
* **`CapabilityService`** updated to accept an optional `routing_config` parameter. When a routing
  entry matches the requested capability it overrides the global provider config.
* **Backward-compatible** — callers that do not supply `routing_config` observe identical behaviour.
* **CLI `model_routing`** config segment (`mind/cli_config.py`):
  * `resolve_cli_config()` now accepts a `model_routing` dict parameter.
  * Falls back to the `MIND_MODEL_ROUTING` environment variable (JSON-encoded dict).

### Key files changed

| File | Change |
|------|--------|
| `mind/capabilities/contracts.py` | Added `CapabilityRoutingConfig` |
| `mind/capabilities/service.py` | `routing_config` param; routing dispatch in `invoke()` |
| `mind/cli_config.py` | `model_routing` field on `ResolvedCliConfig`; env resolution |

---

## γ-4 — Structured Artifact Memory

### What was added

* **`ArtifactIndex`** object type — tree-shaped index nodes for long documents.
  Metadata: `parent_object_id`, `section_id`, `heading`, `summary`, `depth`, `content_range`.
* **`mind/offline/artifact_indexer.py`** — new module:
  * `build_artifact_index(obj, min_content_length)` — splits object content on Markdown headings, produces one `ArtifactIndex` object per section.
  * Objects shorter than `min_content_length` (default 500 chars) are skipped.
* **`REBUILD_ARTIFACT_INDEX`** offline job — batch-indexes all eligible active objects.

### Key files changed / added

| File | Change |
|------|--------|
| `mind/kernel/schema.py` | Added `ArtifactIndex` to schema |
| `mind/offline/artifact_indexer.py` | New module |
| `mind/offline_jobs.py` | `REBUILD_ARTIFACT_INDEX` + `RebuildArtifactIndexJobPayload` |
| `mind/offline/service.py` | `_process_rebuild_artifact_index()` handler |

---

## γ-5 — Memory Decay & Auto-Archive

### What was added

* **`AUTO_ARCHIVE`** offline job — archives stale objects that satisfy all of:
  * Type is `RawRecord` or `SummaryNote` (ephemeral types eligible for decay).
  * Age ≥ `stale_days` (default 90 days).
  * No positive feedback (`feedback_positive_count` = 0 or absent).
  * `dry_run=True` mode reports eligible objects without modifying the store.
* **`OfflineJobScheduler.schedule_auto_archive()`** — enqueues the weekly scan job.
* **`mind unarchive --object-id`** CLI sub-command (`mind/product_cli.py`) — provides a user-facing
  path to restore mis-archived objects (note: full store-level restoration requires the Python API;
  the CLI surfaces a diagnostic response for remote/API-backed flows).
* **`ArchiveReport`** eval metric (`mind/eval/growth_metrics.py`):
  * Fields: `archived_count`, `unarchived_count`, `total_objects`, `archive_rate`, `misarchive_rate`.
  * `gamma_gate_pass` — True when `misarchive_rate ≤ 0.10`.

### Key files changed

| File | Change |
|------|--------|
| `mind/offline_jobs.py` | `AUTO_ARCHIVE` + `AutoArchiveJobPayload` |
| `mind/offline/service.py` | `_process_auto_archive()` handler |
| `mind/offline/scheduler.py` | `schedule_auto_archive()` |
| `mind/product_cli.py` | `unarchive` sub-command |
| `mind/eval/growth_metrics.py` | `ArchiveReport` dataclass |

---

## Test coverage

| Test module | Tests | Notes |
|-------------|-------|-------|
| `tests/test_new_object_types.py` | 27 | Schema, CRUD, promotion, job kinds, workspace boost |
| `tests/test_graph_retrieval.py` | 21 | Adjacency index, BFS expand, concealment, access modes |
| `tests/test_model_routing.py` | 12 | CapabilityRoutingConfig, service routing, CLI config |
| `tests/test_artifact_memory.py` | 17 | ArtifactIndex schema, indexer, section extraction |
| `tests/test_auto_archive.py` | 21 | Archive job, dry_run, ArchiveReport, scheduler, CLI |
| `tests/test_phase_gamma_gate.py` | 44 | Full acceptance gate across all γ sub-tasks |

**All Phase α and Phase β gate tests continue to pass (zero regressions introduced).**

---

## Architecture notes

* All new object types follow the existing `CORE_OBJECT_TYPES` / `REQUIRED_METADATA_FIELDS` pattern.
* All new offline job kinds follow the `process_job` dispatch pattern in `OfflineMaintenanceService`.
* Graph expansion is designed to be **additive and non-disruptive**: new IDs are appended with a
  reduced score so they cannot displace existing high-quality retrieval candidates.
* The `DISCOVER_LINKS` job is idempotent at the object level — it creates new proposed `LinkEdge`
  objects without modifying existing ones.
* `CapabilityRoutingConfig` is fully backward-compatible; the existing `CapabilityService` default
  path is unchanged when `routing_config=None`.
