# Hermes Three-Layer Memory Rules

AgentFlow uses a Hermes-style memory stack for chat context. The goal is to keep conversations continuous without letting noisy turns, accidental instructions, or private details permanently pollute the agent.

## Layer 1: Recent Turns

- Source: recent uncompacted `session_messages`.
- Purpose: preserve immediate conversational continuity.
- Included content: recent user and assistant turns in append-only sequence order.
- Retention: once the session exceeds the compaction threshold, older recent turns can be folded into Layer 2 and marked `compacted`.

## Layer 2: Compressed Session Summary

- Source: `sessions.compact_summary`.
- Purpose: keep durable session state after the raw message window grows too large.
- Compression rules:
  - Preserve user goals, constraints, decisions, tool/API outcomes, useful IDs, and unresolved tasks.
  - Drop greetings, repeated wording, and low-value chatter.
  - Merge new summaries with the existing summary instead of replacing useful prior facts.
- Trigger: `AGENTFLOW_MEMORY_COMPACTION_TOKENS`, default `2400` estimated tokens.

## Layer 3: Long-Term Memory And Rules

- Source: `memories` table.
- Purpose: persist explicit user preferences, durable rules, and stable facts across sessions.
- Current automatic write policy is conservative:
  - Save only when the user explicitly says things like `记住`, `以后`, `偏好`, `规则`, `不要`, `默认`, `remember`, `always`, or `never`.
  - Mark source as `auto_hermes`.
  - Use confidence `0.85`.
- Do not automatically store:
  - One-off task details.
  - Sensitive personal data unless the user explicitly asks to remember it.
  - Model hallucinations or inferred preferences.
  - Temporary debugging state that is not meant to survive the session.

## Prompt Assembly Order

The chat prompt receives memory in this order:

1. Agent system prompt and description.
2. Hermes Layer 1 recent turns.
3. Hermes Layer 2 compressed session summary.
4. Hermes Layer 3 recalled long-term memory and rules.
5. Skill description catalog.
6. Loaded `SKILL.md`, only if the Skill Router selected a skill.
7. Current user input.

## Evolution Rule

Memory rules should evolve through review:

- Automatic writes may create memory records, but operators can inspect them in Runtime Memory.
- Skill Evaluation suggestions must not automatically rewrite `SKILL.md`.
- Any future automatic memory extraction using an evaluator model must keep the same conservative policy and expose its evidence.
