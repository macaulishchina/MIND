# Check: human-doc-sync

## Purpose

Verify that `.human/` still covers the developer-facing meaning of `.ai/`
whenever `.ai/` workflow artifacts change.

## When To Use

- any change that modifies `.ai/`
- any workflow or template change that developers must also read

## Pass Criteria

- Every changed `.ai/` guidance area that matters to developers is reflected in
  some `.human/` handbook section.
- `.human/` stays semantically aligned with `.ai/` even when the document
  structure is different.
- `.human/` remains easier for humans to read and is maintained in Chinese.
- Any intentional omission or delayed update is explicitly documented.

## Acceptable Evidence

- coverage review across the affected topics
- handbook content inspection
- future tooling that maps `.ai/` guidance to `.human/` coverage
