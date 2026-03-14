# Rules: Documentation (`docs/`)

> Load this file when modifying documentation.

---

## Structure

```
docs/
├── index.md                       # Landing page
├── docs-authoring.md             # This authoring guide
├── product/                       # User-facing docs
│   ├── overview.md
│   ├── quickstart.md
│   ├── deployment.md
│   ├── cli.md
│   ├── api.md
│   ├── mcp.md
│   └── sessions-and-users.md
├── reference/                     # Detailed reference
│   ├── cli-reference.md
│   ├── api-reference.md
│   ├── mcp-tool-reference.md
│   ├── config-reference.md
│   └── error-reference.md
├── ops/                           # Runbooks
│   ├── runbook-deploy.md
│   ├── runbook-docs-release.md
│   ├── runbook-upgrade.md
│   ├── runbook-troubleshooting.md
│   └── security.md
├── architecture/                  # Architecture docs
│   ├── system-overview.md
│   ├── app-layer.md
│   ├── storage-model.md
│   ├── transport-model.md
│   └── documentation-system.md
├── foundation/                    # Historical (not in build)
├── design/                        # Historical (not in build)
├── reports/                       # Historical (not in build)
└── research/                      # Historical (not in build)
```

## Rules

1. **Sync with code**: When code changes, update the corresponding docs
   immediately (see `CHANGE_PROTOCOL.md`, "Documentation Sync Rules").

2. **Language**: Documentation is in **Chinese** (matches existing docs and
   `mkdocs.yml` lang=zh setting). Code comments and `.ai/` files are in English.

3. **Strict build**: Run `uv run mkdocs build --strict` before committing
   docs changes. Fix all warnings.

4. **No broken links**: Relative links must resolve. Cross-link between
   product and reference docs where appropriate.

5. **Historical docs**: Do NOT modify files in `foundation/`, `design/`,
   `reports/`, `research/`. They are frozen evidence from completed phases.

6. **Architecture docs**: Update when system boundaries, layers, or key
   patterns change. These are living documents.

7. **API reference**: Must match actual endpoint definitions exactly.
   Include request/response examples.

## Local Preview

```bash
./scripts/dev.sh              # Full dev env with docs at :18602
# Or standalone:
uv sync --extra docs
uv run mkdocs serve -a 0.0.0.0:18603
```
