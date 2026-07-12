# Task 4 Report: Chat interaction polish and retry

## Status

Implemented the Task 4 Chat interaction polish without changing the global Agent selector, responsive shell, Runs components, Tool/MCP features, or deployment behavior.

## Delivered behavior

- Extracted `MessageBubble`, `ThinkingTrace`, and `ChatComposer` from `ChatPanel`.
- Added Chinese-localized message time, assistant-copy action, and success/failure Toast feedback.
- Limited collapsed Trace output to the latest five relevant events, with full expand/collapse controls and distinct running/error summaries.
- Added `FailedSendSnapshot` and `retryLastMessage()` to the Chat store.
- Captured a cloned snapshot of the original message, `executionMode`, and `workflowId` for both HTTP/stream failures.
- Retried from the captured snapshot rather than current composer selections, and cleared the snapshot after a successful retry.
- Blocked retry when the captured Workflow is no longer published for the current Agent, with a Chinese explanation.
- Cleared messages and Trace synchronously before loading a newly selected Agent, and ignored late responses from a previously selected Agent.
- Preserved Enter to send and Shift+Enter for a newline; translated surrounding Chat copy while retaining Agent/Workflow/Skill terms.

## TDD evidence

### RED

Command:

```text
npm test -- --run components/chat
```

Result: exit 1. Three suites failed because the extracted components did not exist. Store tests failed because `failedSendSnapshot` remained `null` and Agent switching retained the previous session while awaiting the request.

Self-review found one additional retry isolation case. Command:

```text
npm test -- --run components/chat/ChatComposer.test.tsx
```

Result: exit 1, 1 failed / 2 passed. The original snapshot retry was incorrectly disabled when only new sends were blocked by the current Workflow selection.

### GREEN

Focused command after the initial implementation:

```text
npm test -- --run components/chat
```

Result: exit 0, 4 files passed / 9 tests passed.

Focused command after the self-review fix:

```text
npm test -- --run components/chat/ChatComposer.test.tsx
```

Result: exit 0, 1 file passed / 3 tests passed.

## Final verification

```text
npm test -- --run
```

Exit 0: 10 test files passed, 42 tests passed.

```text
npx tsc --noEmit --incremental false
```

Exit 0 with no diagnostics.

```text
npm run build
```

Exit 0: Next.js 15.5.18 compiled successfully and generated 12/12 static pages. The generated `apps/web/.next` directory was removed afterward.

```text
pytest apps/api/tests/test_chat_workflow_mode.py apps/api/tests/test_chat_streaming_skill_creator.py -q
```

Completed in 84.22 seconds: 5 passed, 6 failed. All six failures were environment-dependent TestClient requests that attempted to connect to MySQL at `localhost:3306` and received connection refused (`pymysql.err.OperationalError`); no Task 4 frontend failure was reported.

```text
git diff --check
```

Exit 0.

## Self-review

- Scope: only Chat page/panel/store, the three requested components, focused tests, and this report are included.
- Retry integrity: snapshots clone the options object; retries use captured Agent/org/user/message/mode/Workflow values.
- Retry safety: captured Workflow availability is checked against published Workflows, while current composer validation does not incorrectly block a valid captured retry.
- Agent switching: local content is cleared before the network await and stale cross-Agent responses are discarded.
- Regression: full Web tests, TypeScript, and production build pass; `.next` is absent.
- Remaining concern: the two API test files require a reachable local MySQL service for six integration cases. This environment had no MySQL listener on port 3306.

## Review fix: cross-Agent stream isolation

### Findings and root cause

- An in-flight `sendMessage` stream closed over the global Zustand setter without a request-generation check. Starting `loadLatestSession` for another Agent cleared the UI, but late token/error/run-finished frames and the old send's catch/final path could still overwrite the new Agent state.
- `ChatPanel` rendered store messages before its Agent-change effect ran, allowing one paint of the previous Agent's messages.
- An SSE `error` appended a failed event but left earlier `node_started` events running, so Trace could continue to announce “执行中”.
- HTTP/SSE fallback strings were English, and the Shift+Enter test verified only that no send occurred rather than that a controlled newline remained editable.

### Review RED

```text
npm test -- --run components/chat
```

Exit 1: 3 files failed / 2 passed; 6 tests failed / 10 passed. The failures reproduced late old-stream mutation of the new Agent's message, session, Trace, failure snapshot, and generating state; old-message first-paint leakage; running Trace after error; and English HTTP/SSE fallback text.

The ChatPanel test harness was then corrected to provide jsdom's missing `scrollIntoView`; its isolated RED failed on the intended assertion because the old Agent message remained in the document after rerender.

### Review GREEN and implementation

- Added a module-scoped monotonically increasing Chat generation. Every send captures its generation and checks both generation and Agent before all SSE, catch, and post-await writes.
- Starting any send, `loadLatestSession`, or clearing the session invalidates older streams. Session loads also compare their captured generation, covering same-Agent load/send races.
- Added an Agent identity render gate in `ChatPanel`; mismatched store messages, Trace, generating state, and retry snapshot remain hidden until the selected Agent state matches.
- SSE errors now settle every running Trace entry as failed before appending the error, and failure takes precedence in the Trace heading.
- HTTP, network, and SSE errors use Chinese fallback prefixes while retaining available response/backend detail.
- Shift+Enter now has a controlled textarea test that verifies the multiline value and then verifies Enter sends that exact value.

```text
npm test -- --run components/chat
```

Exit 0: 5 files passed, 16 tests passed.

### Review final verification

```text
npm test -- --run
```

Exit 0: 11 test files passed, 48 tests passed.

```text
npx tsc --noEmit --incremental false
```

Exit 0 with no diagnostics.

```text
npm run build
```

Exit 0: Next.js 15.5.18 compiled successfully and generated 12/12 static pages. `apps/web/.next` was removed after verification.

```text
pytest apps/api/tests/test_chat_workflow_mode.py apps/api/tests/test_chat_streaming_skill_creator.py -q
```

Completed in 83.80 seconds: 5 passed, 6 failed. As in the initial Task 4 run, all six integration failures were caused by `localhost:3306` refusing the MySQL connection; no frontend or stream-isolation regression was reported.

```text
git diff --check
```

Exit 0.

### Review self-check

- A delayed-stream regression emits token, error, and run-finished frames after Agent switch and proves the new Agent's message, session ID, Trace, failure snapshot, and generating state are unchanged.
- The render-gate test rerenders `ChatPanel` with a new Agent prop while the mocked store still belongs to the old Agent and proves the old message is absent immediately.
- Trace sequence, HTTP non-OK, empty/detail SSE errors, and controlled Shift+Enter behavior are covered directly.
- No responsive shell, global Agent selector, Runs, Tool/MCP, API implementation, or deployment files were modified.

## Final review fix: session reset completeness

### Root cause and RED

The request-generation invalidation correctly stopped late stream writes, but the synchronous state resets were incomplete: `clearSession` did not reset `isGenerating`, `loadLatestSession` did not clear `intent/subtaskCount`, and the ChatPanel Agent gate still rendered intent directly from the unmatched store state.

```text
npm test -- --run components/chat/ChatStore.test.ts components/chat/ChatPanel.test.tsx
```

Exit 1: 2 files failed; 3 tests failed / 5 passed. Evidence showed `isGenerating: true` immediately after clearing, old intent/subtask values after starting the next Agent load, and old intent text remaining in the DOM after an Agent prop rerender.

### GREEN

- `clearSession` now invalidates the previous generation and synchronously resets session, messages, Trace, failed snapshot, intent, subtask count, and `isGenerating`.
- The delayed-stream regression proves a late token/run-finished sequence cannot repopulate the cleared state.
- `loadLatestSession` synchronously clears intent and subtask count with the rest of the previous Agent state.
- ChatPanel derives visible intent/subtask values through the same Agent identity gate as messages and Trace.

```text
npm test -- --run components/chat/ChatStore.test.ts components/chat/ChatPanel.test.tsx
```

Exit 0: 2 files passed, 8 tests passed.

### Final verification

```text
npm test -- --run
```

Exit 0: 11 test files passed, 49 tests passed.

```text
npx tsc --noEmit --incremental false
```

Exit 0 with no diagnostics.

```text
npm run build
```

Exit 0: Next.js 15.5.18 compiled successfully and generated 12/12 static pages. `apps/web/.next` was removed afterward.

```text
git diff --check
```

Exit 0.

The API regressions were not rerun for this final UI/store-only review fix, as requested. The previously recorded MySQL `localhost:3306` environment limitation remains the only concern.
