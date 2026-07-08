# Workspace Navigation Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the workspace recovery UX so users can always return to workspace setup and cannot accidentally enter Chat with empty workspace or agent context.

**Architecture:** Keep recovery behavior in small frontend UI boundaries. Reuse the existing `WorkspaceRequired` component for missing workspace state, add a Chat-specific no-agent empty state in `app/chat/page.tsx`, and make the Sidebar expose a permanent home/workspace setup route.

**Tech Stack:** Next.js App Router, React client components, Zustand stores, Tailwind CSS classes, lucide-react icons.

## Global Constraints

- Do not change backend APIs or database behavior.
- Do not alter persisted workspace schema.
- Keep UI styling aligned with the existing white, blue, gray AgentFlow palette.
- Keep cards at `rounded-lg` or smaller.
- Use `next/link` for navigation links.
- Use lucide-react icons where an icon is needed.
- Each task must be independently buildable with `npm.cmd run build` from `apps/web`.

---

## File Structure

- `apps/web/app/chat/page.tsx`: owns Chat route state gates for missing workspace and missing selected Agent.
- `apps/web/components/layout/Sidebar.tsx`: owns global navigation and permanent access to Studio home/workspace setup.
- Existing `apps/web/components/ui/WorkspaceRequired.tsx`: reused as-is by Chat; do not modify it in this plan.

---

### Task 1: Guard Chat Workspace And Agent Context

**Files:**
- Modify: `apps/web/app/chat/page.tsx`

**Interfaces:**
- Consumes: `WorkspaceRequired` from `@/components/ui/WorkspaceRequired`.
- Consumes: `workspace`, `agents`, `selectedAgentId`, `setSelectedAgentId` from `useWorkspaceStore`.
- Produces: Chat route returns `WorkspaceRequired` when no workspace exists, and an actionable Agent empty state when workspace exists but no Agent is selected.

- [ ] **Step 1: Add imports**

In `apps/web/app/chat/page.tsx`, add:

```tsx
import Link from "next/link";
import { Bot } from "lucide-react";
import WorkspaceRequired from "@/components/ui/WorkspaceRequired";
```

- [ ] **Step 2: Add missing workspace guard before calculating IDs**

After local state declarations and before deriving `orgId`, `actorUserId`, or `agentId`, add:

```tsx
if (!workspace) {
  return <WorkspaceRequired />;
}
```

Then simplify the ID derivation to:

```tsx
const orgId = workspace.orgId;
const actorUserId = workspace.userId;
const agentId = selectedAgentId || "";
```

- [ ] **Step 3: Replace the no-agent dead end with an actionable state**

Replace the existing `agentId ? (...) : (...)` fallback content with:

```tsx
<div className="flex h-full items-center justify-center px-4">
  <div className="w-full max-w-md rounded-lg border border-[#dfe4ee] bg-white px-6 py-8 text-center shadow-sm">
    <div className="mx-auto grid h-12 w-12 place-items-center rounded-lg bg-[#eef4ff] text-[#2f6feb]">
      <Bot size={22} />
    </div>
    <h2 className="mt-4 text-base font-semibold text-[#172033]">请选择或创建 Agent</h2>
    <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-[#667085]">
      Chat 需要一个 Agent 作为运行主体。你可以在 Agents 页面创建 Agent，或从上方选择已有 Agent。
    </p>
    <Link
      className="mt-5 inline-flex h-9 items-center justify-center rounded-lg bg-[#2f6feb] px-4 text-sm font-medium text-white transition hover:bg-[#255dc7]"
      href="/agents"
    >
      前往 Agents
    </Link>
  </div>
</div>
```

- [ ] **Step 4: Verify Chat build**

Run:

```bash
cd apps/web
npm.cmd run build
```

Expected: build exits with code 0.

- [ ] **Step 5: Commit**

```bash
git add apps/web/app/chat/page.tsx
git commit -m "fix: guard chat workspace and agent context"
```

---

### Task 2: Add Permanent Home Entry To Sidebar

**Files:**
- Modify: `apps/web/components/layout/Sidebar.tsx`

**Interfaces:**
- Consumes: current `navItems` array and active route matching.
- Produces: a visible `Home` navigation item linked to `/`, and the AgentFlow brand area links to `/`.

- [ ] **Step 1: Add Home icon import**

In `apps/web/components/layout/Sidebar.tsx`, add `House` to the lucide-react import list:

```tsx
House,
```

- [ ] **Step 2: Add Home as the first navigation item**

Change `navItems` so the first item is:

```tsx
{ key: "home", label: "Home", icon: House, href: "/" },
```

Keep the existing module order after `Home`.

- [ ] **Step 3: Make active matching exact for Home**

Replace the active calculation inside the nav map with:

```tsx
const active = item.href === "/" ? pathname === "/" : pathname === item.href || pathname?.startsWith(item.href + "/");
```

- [ ] **Step 4: Link the brand area to Home**

Replace the brand wrapper `<div className="flex items-center gap-3 border-b ...">...</div>` with a `Link`:

```tsx
<Link
  className="flex items-center gap-3 border-b border-[#dfe4ee] px-5 py-4 transition hover:bg-[#f8fafc]"
  href="/"
>
  ...
</Link>
```

Preserve the existing logo, title, and subtitle.

- [ ] **Step 5: Verify Sidebar build**

Run:

```bash
cd apps/web
npm.cmd run build
```

Expected: build exits with code 0.

- [ ] **Step 6: Commit**

```bash
git add apps/web/components/layout/Sidebar.tsx
git commit -m "feat: add home entry to sidebar"
```

---

### Task 3: Integration Verification

**Files:**
- Read: `apps/web/app/chat/page.tsx`
- Read: `apps/web/components/layout/Sidebar.tsx`

**Interfaces:**
- Consumes: commits from Task 1 and Task 2.
- Produces: verification evidence that workspace recovery remains available globally.

- [ ] **Step 1: Search for remaining dead-end workspace copy**

Run:

```bash
rg -n "Create a workspace first|请先创建工作空间|请先在首页创建工作空间|Select an Agent to start" apps/web/app apps/web/components -g "*.tsx"
```

Expected: no output.

- [ ] **Step 2: Run frontend build**

Run:

```bash
cd apps/web
npm.cmd run build
```

Expected: build exits with code 0.

- [ ] **Step 3: Commit verification-only cleanup if needed**

If Step 1 finds stale copy, remove it in the owning file and commit:

```bash
git add apps/web
git commit -m "fix: remove stale recovery dead ends"
```

If no stale copy exists, do not create a commit.
