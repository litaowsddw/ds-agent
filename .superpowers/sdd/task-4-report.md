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
