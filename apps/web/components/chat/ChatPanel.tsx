"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useChatStore, type ChatExecutionMode } from "@/stores/chat";
import ChatComposer from "@/components/chat/ChatComposer";
import MessageBubble from "@/components/chat/MessageBubble";
import ThinkingTrace from "@/components/chat/ThinkingTrace";
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
  const {
    sessionId,
    messages,
    sessions,
    traceEvents,
    isGenerating,
    intent,
    subtaskCount,
    failedSendSnapshot,
    sendMessage,
    retryLastMessage,
    loadLatestSession,
    loadSessionHistory,
    loadMessages,
    clearSession,
  } = useChatStore();
  const isCurrentAgent = useChatStore((state) => state.agentId) === agentId;
  const visibleMessages = isCurrentAgent ? messages : [];
  const visibleTraceEvents = isCurrentAgent ? traceEvents : [];
  const visibleIsGenerating = isCurrentAgent && isGenerating;
  const visibleFailedSnapshot = isCurrentAgent ? failedSendSnapshot : null;
  const visibleIntent = isCurrentAgent ? intent : "";
  const visibleSubtaskCount = isCurrentAgent ? subtaskCount : 0;
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
  const isComposerDisabled = !isCurrentAgent || visibleIsGenerating || Boolean(workflowModeBlockedReason);
  const retryBlockedMessage =
    visibleFailedSnapshot?.options.executionMode === "workflow" &&
    (!visibleFailedSnapshot.options.workflowId ||
      !publishedWorkflows.some((workflow) => workflow.workflow_id === visibleFailedSnapshot.options.workflowId))
      ? "上次消息使用的 Workflow 已不可用，请重新选择后发送。"
      : "";

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [visibleMessages, visibleTraceEvents, visibleIsGenerating]);

  useEffect(() => {
    void loadLatestSession(agentId, actorUserId);
    void loadSessionHistory(agentId, actorUserId);
  }, [agentId, actorUserId, loadLatestSession, loadSessionHistory]);

  const formatSessionLabel = (session: (typeof sessions)[number]) => {
    const summary = session.compact_summary.trim();
    if (summary) return summary.length > 28 ? `${summary.slice(0, 28)}…` : summary;
    const timestamp = new Date(session.updated_at || session.created_at);
    const date = Number.isNaN(timestamp.getTime()) ? "" : timestamp.toLocaleString();
    return date ? `会话 · ${date}` : `会话 · ${session.session_id.slice(-8)}`;
  };

  useEffect(() => {
    const defaultWorkflow = defaultWorkflowId
      ? publishedWorkflows.find((workflow) => workflow.workflow_id === defaultWorkflowId)
      : undefined;
    setWorkflowId(defaultWorkflow?.workflow_id || publishedWorkflows[0]?.workflow_id || "");
  }, [agentId, defaultWorkflowId, publishedWorkflows]);

  const handleSend = async (msg: string) => {
    if (isComposerDisabled) return;
    await sendMessage(agentId, orgId, msg, actorUserId, {
      executionMode,
      workflowId: executionMode === "workflow" ? workflowId : undefined,
    });
  };

  return (
    <div className="flex h-full min-w-0 flex-col">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-[#dfe4ee] bg-white px-4 py-3">
          <div>
            <h3 className="text-sm font-medium text-[#172033]">与 Agent 对话</h3>
            {visibleIntent ? (
              <p className="mt-0.5 text-xs text-[#2f6feb]">
                意图：{visibleIntent} · 子任务：{visibleSubtaskCount}
              </p>
            ) : null}
          </div>
          <button
            onClick={clearSession}
            className="rounded px-2 py-1 text-xs text-[#667085] hover:bg-[#f8fafc]"
            type="button"
          >
            新建对话
          </button>
          <select
            aria-label="会话历史"
            className="ml-2 max-w-52 rounded border border-[#dfe4ee] bg-white px-2 py-1 text-xs text-[#475467]"
            disabled={visibleIsGenerating || sessions.length === 0}
            onChange={(event) => {
              const nextSessionId = event.target.value;
              if (nextSessionId) void loadMessages(nextSessionId);
            }}
            value={isCurrentAgent ? sessionId || "" : ""}
          >
            <option value="">{sessions.length === 0 ? "暂无历史会话" : "选择历史会话"}</option>
            {sessions.map((session) => (
              <option key={session.session_id} value={session.session_id}>
                {formatSessionLabel(session)}
              </option>
            ))}
          </select>
        </div>

        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
          {visibleMessages.length === 0 ? (
            <div className="mt-8 text-center text-[#98a2b3]">
              <p className="text-sm">{isCurrentAgent ? "发送消息，开始与此 Agent 对话" : "正在加载 Agent 对话…"}</p>
              {isCurrentAgent ? <p className="mt-1 text-xs">流式回答和执行 Trace 将显示在这里</p> : null}
            </div>
          ) : null}
          {visibleMessages.map((message, index) => (
            <MessageBubble key={message.message_id || index} message={message} />
          ))}
          <div ref={messagesEndRef} />
        </div>

        <div className="border-t border-[#dfe4ee] bg-white px-4 py-3">
          {visibleTraceEvents.length > 0 ? <ThinkingTrace events={visibleTraceEvents} /> : null}
          <ChatComposer
            disabled={isComposerDisabled}
            retryDisabled={visibleIsGenerating}
            onSend={handleSend}
            onRetry={visibleFailedSnapshot ? retryLastMessage : undefined}
            retryBlockedMessage={retryBlockedMessage}
          >
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
                  Workflow 模式
                </button>
              </div>
              {executionMode === "workflow" ? (
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
              ) : null}
              {workflowModeBlockedReason ? (
                <div className="basis-full rounded-lg bg-[#fff7ed] px-3 py-2 text-xs text-[#9a3412]">
                  {workflowModeBlockedMessage}{" "}
                  <Link className="font-medium text-[#2f6feb] underline" href="/workflows">
                    Workflow 管理
                  </Link>
                </div>
              ) : null}
            </div>
          </ChatComposer>
        </div>
      </div>
    </div>
  );
}
