# Change Proposal: Chat-First Frontend Workbench

## Metadata

- Change ID: `chat-homepage-workbench`
- Type: `feature`
- Status: `archived`
- Spec impact: `update required`
- Verification profile: `full`
- Owner: `Codex`
- Related specs: `interface-foundation`, `frontend-workbench`

## Summary

- Replace the current memory-workbench-first homepage with a chat-first internal
  workbench.
- Add a maintained application/REST chat path so the frontend can run normal
  LLM conversations instead of only posting memory ingestions.
- Expose a TOML-driven, curated set of selectable chat model profiles to the
  frontend while keeping STL and decision model selection backend-only.
- Keep explicit memory submission as a separate test action, and submit only the
  conversation turns that have not already been submitted.

## Why Now

- The current frontend is useful as a memory CRUD/debug surface, but it is not a
  natural way to experience MIND as an end-to-end conversational system.
- The repository now has an application layer and maintained REST adapter, so
  this is the right point to add a chat-facing interface without coupling the
  frontend to kernel details.
- Doing this before v1.5 keeps future MCP / CLI / web work aligned on one
  canonical chat-facing contract instead of retrofitting a UI-only prototype.

## In Scope

- Add a maintained chat operation to the application layer.
- Add REST endpoints for chat completion and chat-model profile discovery.
- Add TOML config for curated, frontend-selectable chat model profiles.
- Redesign the frontend homepage into a chat-first layout inspired by standard
  LLM chat products.
- Keep a memory explorer surface for inspection, update, delete, and history.
- Track submitted vs unsubmitted conversation turns in the frontend and send
  only unsubmitted turns to memory ingestion.

## Out Of Scope

- MCP and CLI adapters.
- Authentication, tenancy, or user accounts.
- Streaming responses, WebSockets, and server-pushed partial tokens.
- Exposing STL extraction or decision model controls in the frontend.
- Converting the frontend into a polished public product site.

## Proposed Changes

- Extend `mind/application/` with a chat request/response contract and a
  `chat_completion` operation that uses an LLM config resolved from a curated
  chat-profile registry.
- Extend central TOML parsing with a chat profile section, including:
  - profile id
  - label
  - provider
  - optional model / temperature / timeout overrides
  - one default profile id
- Add REST endpoints such as:
  - `GET /api/v1/chat/models`
  - `POST /api/v1/chat/completions`
- Keep `/api/v1/ingestions` as the memory write path, but shift the frontend so
  ingestion is a secondary test action attached to the live chat transcript.
- Redesign the frontend into:
  - a main chat window with message history, composer, send action, and model
    selector sourced from REST
  - a conversation-tools area with actions like `Submit Memory`
  - a side or secondary panel for `Memory Explorer`
- Track a submission cursor in the frontend so clicking `Submit Memory` sends
  only the new turns since the last successful ingestion for that conversation.
- Preserve the current owner selector model (`external_user_id` vs
  `anonymous_session_id`) for both chat and memory actions.

## Reality Check

- The current repository does not have a maintained chat API at all. Simply
  replacing the page with a chat UI would create a shell without a backend
  contract, so the chat service must be added first-class to the application and
  REST layers.
- Exposing the raw `[llm.*]` provider table directly to the frontend would be a
  bad fit. It would leak backend implementation choices and make STL/decision
  profiles accidentally selectable. A curated chat-profile section is the safer
  contract.
- The phrase “参考 openai 官网实现，甚至直接抄也行” is useful as a style target,
  but the repository should still keep an internal-workbench identity rather
  than a literal product clone. The better direction is a chat-first workbench
  visually inspired by that pattern.
- A frontend-only “submit only unsubmitted dialogue” guarantee is only strong
  within the client state it retains. To reduce accidental double-submission on
  refresh, the frontend should persist the transcript and submission cursor in
  browser storage for the active workbench session.
- This change touches config, application layer, REST contracts, frontend UX,
  and tests at once, so it should be treated as one substantial feature change
  with `full` verification rather than a quick UI tweak.

## Acceptance Signals

- The main frontend surface is a chat-first UI rather than the current
  ingestion/search form layout.
- A developer can choose among the configured chat model profiles in the
  frontend, send messages, and receive assistant replies through REST.
- The frontend cannot switch STL extraction or decision-stage models.
- Clicking `Submit Memory` ingests only the turns that have not already been
  submitted for the active conversation.
- Memory Explorer still supports list, detail, update, delete, and history.
- Automated tests cover the new application, REST, and frontend behaviors.

## Verification Plan

- Use the `full` profile.
- Run `pytest tests/` to cover config, application, and REST regressions.
- Add targeted REST tests for chat-model discovery and chat completion.
- Run `npm run test` and `npm run build` in `frontend/`.
- Record a manual smoke path covering:
  - choose a chat model
  - send chat messages
  - submit only new turns to memory
  - inspect resulting memories in Memory Explorer

## Open Questions

- None blocking for proposal approval. The implementation assumption is that the
  workbench will persist the active transcript and submission cursor in browser
  storage so accidental refresh does not lose the “already submitted” boundary.

## Approval

- [x] Proposal reviewed
- [x] Important conflicts and feasibility risks surfaced
- [x] Spec impact confirmed
- [x] Ready to finalize tasks and implement
