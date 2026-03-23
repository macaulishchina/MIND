# Living Specs

Use `.ai/specs/` for approved, current behavior only.

## Rules

- One capability per subdirectory
- Keep the file name `spec.md`
- Write requirements as current truth, not proposals
- Do not store draft ideas or implementation tasks here

Example layout:

```text
.ai/specs/
  auth/
    spec.md
  search/
    spec.md
```

When a change is still under discussion, place its updates in
`.ai/changes/<change-id>/specs/` instead.
