"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle2, Loader2, Wrench, XCircle } from "lucide-react";
import Link from "next/link";
import { useChatStore, type ChatExecutionMode } from "@/stores/chat";
import type { Agent } from "@/types/agent";
import type { WorkflowItem } from "@/types/workflow";

export default function ChatPanel({
  agentId,
  orgId,
  actorUserId,
  workflows,
  agent,
}: {
  agentId: string;
  orgId: string;
  actorUserId: string;
  workflows: WorkflowItem[];
  agent: Agent | null;
}) {
  const { messages, traceEvents, isGenerating, intent, subtaskCount, sendMessage, loadLatestSession, clearSession } =
    useChatStore();
  const [input, setInput] = useState("");
  const [executionMode, setExecutionMode] = useState<ChatExecutionMode>("autonomous");
  const [workflowId, setWorkflowId] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const defaultWorkflowId = agent?.default_workflow_id ?? null;
  const publishedWorkflows = useMemo(
    () => workflows.filter((workflow) => workflow.agent_id === agentId && workflow.published_version_id),
    [agentId, workflows]
  );
  const workflowModeBlockedReason =
    executionMode !== "workflow"
      ? ""
      : publishedWorkflows.length === 0
        ? "暂无已发布 Workflow"
        : !workflowId
          ? "请选择已发布 Workflow"
          : "";
  const workflowModeBlockedMessage =
    workflowModeBlockedReason === "暂无已发布 Workflow"
      ? "当前 Agent 还没有可用的已发布 Workflow。请先发布流程，或切回自主模式。"
      : workflowModeBlockedReason === "请选择已发布 Workflow"
        ? "请选择一个已发布 Workflow 后再发送消息。"
        : "";
  const isSendDisabled = isGenerating || !input.trim() || Boolean(workflowModeBlockedReason);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, traceEvents, isGenerating]);

  useEffect(() => {
    void loadLatestSession(agentId, actorUserId);
  }, [agentId, actorUserId, loadLatestSession]);

  useEffect(() => {
    const defaultWorkflow = defaultWorkflowId
      ? publishedWorkflows.find((workflow) => workflow.workflow_id === defaultWorkflowId)
      : undefined;
    setWorkflowId(defaultWorkflow?.workflow_id || publishedWorkflows[0]?.workflow_id || "");
  }, [agentId, defaultWorkflowId, publishedWorkflows]);

  const handleSend = async () => {
    if (isSendDisabled) return;
    const msg = input.trim();
    setInput("");
    await sendMessage(agentId, orgId, msg, actorUserId, {
      executionMode,
      workflowId: executionMode === "workflow" ? workflowId : undefined,
    });
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex h-full min-w-0 flex-col">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-[#dfe4ee] bg-white px-4 py-3">
          <div>
            <h3 className="text-sm font-medium text-[#172033]">Chat with Agent</h3>
            {intent ? (
              <p className="mt-0.5 text-xs text-[#2f6feb]">
                Intent: {intent} | Subtasks: {subtaskCount}
              </p>
            ) : null}
          </div>
          <button
            onClick={clearSession}
            className="rounded px-2 py-1 text-xs text-[#667085] hover:bg-[#f8fafc]"
            type="button"
          >
            New Chat
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
          {messages.length === 0 ? (
            <div className="mt-8 text-center text-[#98a2b3]">
              <p className="text-sm">Send a message to start chatting with this Agent</p>
              <p className="mt-1 text-xs">Streaming output and backend trace will appear here</p>
            </div>
          ) : null}
          {messages.map((msg, idx) => (
            <div key={msg.message_id || idx} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
                  msg.role === "user"
                    ? "bg-[#2f6feb] text-white"
                    : msg.role === "system"
                      ? "bg-red-50 text-red-600"
                      : "bg-[#f2f4f7] text-[#172033]"
                }`}
              >
                {msg.content ? <p className="whitespace-pre-wrap">{msg.content}</p> : null}
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        <div className="border-t border-[#dfe4ee] bg-white px-4 py-3">
          {traceEvents.length > 0 ? <ThinkingTrace events={traceEvents} /> : null}
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <div className="inline-flex rounded-lg border border-[#dfe4ee] bg-white p-1 text-xs">
              <button
                className={`rounded-md px-3 py-1.5 ${executionMode === "autonomous" ? "bg-[#2f6feb] text-white" : "text-[#667085]"}`}
                onClick={() => setExecutionMode("autonomous")}
                type="button"
              >
                自主模式
              </button>
              <button
                className={`rounded-md px-3 py-1.5 ${executionMode === "workflow" ? "bg-[#2f6feb] text-white" : "text-[#667085]"}`}
                onClick={() => setExecutionMode("workflow")}
                type="button"
              >
                流程模式
              </button>
            </div>
            {executionMode === "workflow" ? (
              <>
                <select
                  className="h-8 rounded-lg border border-[#dfe4ee] bg-white px-2 text-xs text-[#172033] disabled:cursor-not-allowed disabled:opacity-60"
                  disabled={publishedWorkflows.length === 0}
                  onChange={(event) => setWorkflowId(event.target.value)}
                  value={workflowId}
                >
                  <option value="">选择已发布 Workflow</option>
                  {publishedWorkflows.map((workflow) => (
                    <option key={workflow.workflow_id} value={workflow.workflow_id}>
                      {workflow.name}
                    </option>
                  ))}
                </select>
              </>
            ) : null}
            {workflowModeBlockedReason ? (
              <div className="basis-full rounded-lg bg-[#fff7ed] px-3 py-2 text-xs text-[#9a3412]">
                {workflowModeBlockedMessage}{" "}
                <Link className="font-medium text-[#2f6feb] underline" href="/workflows">
                  Workflows
                </Link>
              </div>
            ) : null}
          </div>
          <div className="flex gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Type a message..."
              rows={1}
              className="flex-1 resize-none rounded-lg border border-[#dfe4ee] bg-white px-3 py-2 text-sm text-[#172033] focus:outline-none focus:ring-2 focus:ring-[#2f6feb]"
              disabled={isGenerating}
            />
            <button
              onClick={handleSend}
              disabled={isSendDisabled}
              className="rounded-lg bg-[#2f6feb] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#2459c9] disabled:cursor-not-allowed disabled:opacity-50"
              title={workflowModeBlockedReason || undefined}
              type="button"
            >
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function ThinkingTrace({ events }: { events: ReturnType<typeof useChatStore.getState>["traceEvents"] }) {
  const visibleEvents = events.filter((event) =>
    ["node_started", "node_finished", "skill_created", "error"].includes(event.event)
  );
  const activeEvent = [...visibleEvents].reverse().find((event) => event.status === "running");
  const displayEvents = activeEvent ? visibleEvents : visibleEvents.slice(-5);

  return (
    <div className="mb-3 rounded-lg border border-[#dfe4ee] bg-[#f8fafc] px-3 py-2 text-xs">
      <div className="mb-2 flex items-center gap-2 text-[#2f6feb]">
        {activeEvent ? (
          <Loader2 size={13} className="animate-spin" />
        ) : (
          <CheckCircle2 size={13} className="text-emerald-500" />
        )}
        <span className="font-medium">{activeEvent ? "执行中" : "执行 Trace"}</span>
        {activeEvent ? <span className="truncate text-[#667085]">{activeEvent.label || activeEvent.node}</span> : null}
      </div>
      <div className="space-y-1">
        {displayEvents.map((event) => (
          <div key={event.id} className="rounded bg-white px-2 py-1.5">
            <div className="flex items-start gap-2">
              <TraceIcon status={event.status} event={event.event} />
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium text-[#172033]">
                  {event.label || event.node || event.event}
                </div>
                {renderTraceDetail(event)}
                {event.event === "skill_created" ? (
                  <div className="mt-1 rounded bg-emerald-50 px-2 py-1 text-emerald-700">
                    {String(event.data.name || "Skill created")}
                  </div>
                ) : null}
                {event.event === "error" ? <div className="mt-1 text-red-500">{String(event.data.error || "error")}</div> : null}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function renderTraceDetail(event: ReturnType<typeof useChatStore.getState>["traceEvents"][number]) {
  const agentName = typeof event.data.agent_name === "string" ? event.data.agent_name : "";
  const supervisorName = typeof event.data.supervisor_name === "string" ? event.data.supervisor_name : "";
  const model = typeof event.data.model_name === "string" ? event.data.model_name : "";
  const skillTopic = typeof event.data.skill_topic === "string" ? event.data.skill_topic : "";
  const workflowRunId = typeof event.data.workflow_run_id === "string" ? event.data.workflow_run_id : "";
  if (workflowRunId) {
    return <div className="mt-0.5 truncate text-[#667085]">Run {workflowRunId}</div>;
  }
  const detail = skillTopic || agentName || supervisorName || model || event.event;
  return <div className="mt-0.5 truncate text-[#667085]">{detail}</div>;
}

function TraceIcon({ status, event }: { status: string; event: string }) {
  if (event === "skill_created") return <Wrench size={14} className="mt-0.5 text-emerald-500" />;
  if (status === "running") return <Loader2 size={14} className="mt-0.5 animate-spin text-blue-500" />;
  if (status === "failed") return <XCircle size={14} className="mt-0.5 text-red-500" />;
  if (status === "succeeded") return <CheckCircle2 size={14} className="mt-0.5 text-emerald-500" />;
  return <CheckCircle2 size={14} className="mt-0.5 text-gray-300" />;
}
