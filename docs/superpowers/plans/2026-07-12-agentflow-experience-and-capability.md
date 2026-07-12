# AgentFlow Experience and Capability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve Agent context across pages, support narrow screens, make runs diagnosable, improve Chat, and publish a protected public deployment.

**Architecture:** Zustand remains the single client-context source. Large page renderers split into focused components. Workflow Run responses expose only timestamps already stored by the ORM. Caddy provides same-origin routing and Basic Auth before a Cloudflare HTTPS quick tunnel.

**Tech Stack:** Next.js 15, React 19, TypeScript 5.7, Zustand 5, Tailwind CSS 3, Vitest, Testing Library, FastAPI, Pydantic, pytest, Docker Compose, Caddy, cloudflared.

## Global Constraints

- Four feature commits: global Agent context, responsive shell, Runs observability, and Chat polish.
- Do not replace the visual brand, execution protocol, state library, or UI framework.
- Keep Agent, Workflow, and Skill as product terms; translate surrounding UI into Chinese.
- Missing time, duration, or Workflow metadata renders as `—`; never fabricate values.
- Each feature includes tests, passes `git diff --check`, and is pushed to `feat/agent-default-workflow`.
- Deployment secrets and live credentials never enter Git.

## File Map

- `components/layout/AgentContextSelect.tsx`: global Agent selection.
- `components/layout/MobileNavOverlay.tsx`: accessible mobile navigation.
- `components/ui/AgentRequired.tsx`: missing-Agent recovery.
- `components/runs/*`: list, status, summary, node card, JSON disclosure.
- `components/chat/{MessageBubble,ThinkingTrace,ChatComposer}.tsx`: Chat presentation.
- `test/setup.ts`, `vitest.config.ts`: component-test foundation.
- `schemas/workflow_run.py`, `routes/workflow_runs.py`: real timestamp contract.
- `deploy/Caddyfile`, `docker-compose.production.yml`: protected deployment.

---

### Task 1: Global Agent context

**Files:** Create `apps/web/vitest.config.ts`, `apps/web/test/setup.ts`, `apps/web/components/layout/AgentContextSelect.tsx`, its `.test.tsx`, and `apps/web/components/ui/AgentRequired.tsx`. Modify `apps/web/package.json`, lockfile, `stores/workspace.ts`, `components/layout/Header.tsx`, and Chat/Workflows/Runs pages.

**Interfaces:** Consume `agents`, `selectedAgentId`, `setSelectedAgentId`, `refreshAgents`; produce `AgentContextSelect()` and `AgentRequired({ description? })`.

- [ ] Write failing tests for empty/current selection, change events, and stale selection cleanup. Configure jsdom and `@` alias. Required behavior:

```ts
setAgents: (agents) => set((state) => ({
  agents,
  selectedAgentId: agents.some((a) => a.agent_id === state.selectedAgentId)
    ? state.selectedAgentId : agents.length === 1 ? agents[0].agent_id : "",
})),
```

- [ ] From `apps/web`, run `npm test -- --run components/layout/AgentContextSelect.test.tsx`; expect FAIL because configuration/component/cleanup is absent.
- [ ] Implement selector, disable while busy, link to `/agents` when empty, mount in Header, remove Chat's duplicate select, and use `AgentRequired` in Workflows/Runs.
- [ ] Run `npm test -- --run`, `npx tsc --noEmit --incremental false`, and `npm run build`; expect all exit 0.
- [ ] Stage only Task 1 files, commit `feat: add global agent context selector`, and push.

### Task 2: Responsive application shell

**Files:** Create `apps/web/components/layout/MobileNavOverlay.tsx` and test. Modify `AppLayout.tsx`, `Header.tsx`, `Sidebar.tsx`, `app/workflows/page.tsx`, and `app/globals.css`.

**Interfaces:** Header receives `onOpenNavigation`; Sidebar receives optional `mobile` and `onNavigate`; overlay receives `{ open, onClose }`.

- [ ] Write failing tests for Escape, backdrop, navigation dismissal, `aria-hidden`, and Header `aria-expanded`.
- [ ] Run `npm test -- --run components/layout/MobileNavOverlay.test.tsx`; expect FAIL because responsive interfaces are absent.
- [ ] Implement `hidden lg:flex` desktop navigation, fixed mobile drawer, focus return, body-scroll lock, responsive main padding, and close-on-route-change.

```tsx
useEffect(() => {
  if (!open) return;
  const close = (event: KeyboardEvent) => event.key === "Escape" && onClose();
  document.addEventListener("keydown", close);
  document.body.style.overflow = "hidden";
  return () => { document.removeEventListener("keydown", close); document.body.style.overflow = ""; };
}, [open, onClose]);
```

- [ ] Keep Workflow's three columns at `xl`; below `xl`, expose palette/inspector as selectable drawers while preserving the canvas.
- [ ] Run all Web tests, typecheck, and build. Inspect 375×812 and 1280×800; expect no page-level horizontal overflow.
- [ ] Stage only Task 2 files, commit `feat: make application shell responsive`, and push.

### Task 3: Structured Workflow Run diagnostics

**Files:** Create `apps/web/components/runs/{RunStatusBadge,RunList,RunSummary,NodeRunCard,JsonDisclosure}.tsx` and tests. Modify Runs page, `types/workflow.ts`, API workflow-run schema/route, and `apps/api/tests/test_workflow_execution_service.py`.

**Interfaces:** Add `WorkflowRun.created_at: string` and `updated_at: string`; produce status components and `formatElapsed(milliseconds): string`.

- [ ] Write failing API assertions for ISO timestamps and UI tests for known/unknown statuses, filtering, missing values, and `formatElapsed(1530) === "1.53 秒"`.

```python
body = response.json()
assert body["created_at"]
assert body["updated_at"]
```

- [ ] Run focused pytest and `npm test -- --run components/runs`; expect timestamp/component failures.
- [ ] Import `datetime`, add timestamp fields to `WorkflowRunResponse`, map existing `run.created_at`/`run.updated_at` in `_to_run_response`, and mirror in TypeScript.
- [ ] Build status filtering/badges, real times, Workflow labels, failure-first summaries, node duration, and accessible `<details>` raw JSON. Unknown/missing data uses neutral styling/`—`.
- [ ] Run focused pytest, all Web tests, typecheck, and build; expect exit 0.
- [ ] Stage only Task 3 files, commit `feat: improve workflow run observability`, and push.

### Task 4: Chat interaction polish and retry

**Files:** Create `apps/web/components/chat/MessageBubble.tsx`, `ThinkingTrace.tsx`, `ChatComposer.tsx`, and tests. Modify `ChatPanel.tsx`, Chat page, and `stores/chat.ts`.

**Interfaces:** Consume existing `Message`, `ChatTraceEvent`, and `SendMessageOptions`; produce `FailedSendSnapshot`, `retryLastMessage(): Promise<void>`, copy actions, and expandable trace.

- [ ] Write failing tests for localized time, clipboard success/failure, last-five trace, expand/collapse, running/error status, and retry retaining the original mode/Workflow ID.

```ts
interface FailedSendSnapshot {
  agentId: string; orgId: string; actorUserId?: string;
  message: string; options: SendMessageOptions;
}
```

- [ ] Run `npm test -- --run components/chat`; expect FAIL because extracted components and retry state are absent.
- [ ] Store an immutable snapshot on send failure and implement `retryLastMessage`. On Agent change, clear old messages/trace before awaiting the next session; block retry when its Workflow is unavailable.
- [ ] Extract message, trace, and composer components; translate labels, show time, copy assistant text with Toast, and reveal full trace after expansion. Preserve Enter/Shift+Enter.
- [ ] Run all Web tests, typecheck, build, plus `pytest apps/api/tests/test_chat_workflow_mode.py apps/api/tests/test_chat_streaming_skill_creator.py -q`; expect exit 0.
- [ ] Stage only Task 4 files, commit `feat: polish chat interaction experience`, and push.

### Task 5: Protected production deployment

**Files:** Modify `apps/web/Dockerfile`, `docker-compose.yml`, `.env.example`; create `docker-compose.production.yml`, `deploy/Caddyfile`, and `docs/DEPLOYMENT.md`.

**Interfaces:** Produce production Next serving, same-origin `/api`, Basic Auth, localhost-only gateway, health checks, and HTTPS Cloudflare URL.

- [ ] Document checks: authenticated `/api/health` returns 200/`status=ok`; anonymous requests return 401; authenticated Web returns 200; browser reaches Home, Agents, Chat, Workflows, Runs.
- [ ] Run base Compose config/build; confirm initial development Web, unsuitable API origin, and published infrastructure ports.
- [ ] Convert Web image to `npm ci`, `npm run build`, `npm start` with `NEXT_PUBLIC_API_BASE_URL=/api`. Production override removes host publishing from infrastructure/Web/API, adds restart policies, and exposes Caddy only at `127.0.0.1:18080`.
- [ ] Add Basic Auth and routing:

```caddyfile
:8080 {
  basic_auth { {$DEPLOY_USER} {$DEPLOY_PASSWORD_HASH} }
  handle_path /api/* { reverse_proxy api:8000 }
  handle { reverse_proxy web:3000 }
}
```

- [ ] Require external Basic Auth hash, JWT, encryption, database, MinIO, and Grafana secrets; never commit live values.
- [ ] Run production Compose config/build, applicable pytest, Web tests, typecheck, build, local health, and browser smoke; expect pass.
- [ ] Stage only deployment files, commit `chore: add production deployment configuration`, and push.
- [ ] Download official `cloudflared`, start production Compose, run `cloudflared tunnel --url http://127.0.0.1:18080`, verify its `https://*.trycloudflare.com` URL, and report URL, Basic Auth credentials, and deployed commit.

## Final Review

- [ ] Working tree is clean and all five commits are on `origin/feat/agent-default-workflow`.
- [ ] Applicable backend tests, Web tests, typecheck, and production build pass.
- [ ] Five key pages pass desktop/mobile browser smoke checks.
- [ ] Public URL rejects anonymous access, accepts Basic Auth, and `/api/health` is healthy.
