"use client";

import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Loader2, Wrench, XCircle } from "lucide-react";
import { useChatStore } from "@/stores/chat";

export default function ChatPanel({
  agentId,
  orgId,
  actorUserId,
}: {
  agentId: string;
  orgId: string;
  actorUserId: string;
}) {
  const { messages, traceEvents, isGenerating, intent, subtaskCount, sendMessage, loadLatestSession, clearSession } =
    useChatStore();
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, traceEvents, isGenerating]);

  useEffect(() => {
    void loadLatestSession(agentId, actorUserId);
  }, [agentId, actorUserId, loadLatestSession]);

  const handleSend = async () => {
    if (!input.trim() || isGenerating) return;
    const msg = input.trim();
    setInput("");
    await sendMessage(agentId, orgId, msg, actorUserId);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const lastAssistantId = [...messages].reverse().find((msg) => msg.role === "assistant")?.message_id;
  const shouldShowThinking = isGenerating && traceEvents.length > 0;

  return (
    <div className="flex h-full min-w-0 flex-col">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3 dark:border-gray-700">
          <div>
            <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">Chat with Agent</h3>
            {intent ? (
              <p className="mt-0.5 text-xs text-blue-500">
                Intent: {intent} | Subtasks: {subtaskCount}
              </p>
            ) : null}
          </div>
          <button
            onClick={clearSession}
            className="rounded px-2 py-1 text-xs text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
            type="button"
          >
            New Chat
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
          {messages.length === 0 ? (
            <div className="mt-8 text-center text-gray-400 dark:text-gray-500">
              <p className="text-sm">Send a message to start chatting with this Agent</p>
              <p className="mt-1 text-xs">Streaming output and backend trace will appear here</p>
            </div>
          ) : null}
          {messages.map((msg, idx) => (
            <div key={msg.message_id || idx} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
                  msg.role === "user"
                    ? "bg-blue-500 text-white"
                    : msg.role === "system"
                      ? "bg-red-50 text-red-600 dark:bg-red-900/20 dark:text-red-400"
                      : "bg-gray-100 text-gray-900 dark:bg-gray-800 dark:text-gray-100"
                }`}
              >
                {msg.content ? <p className="whitespace-pre-wrap">{msg.content}</p> : null}
                {msg.message_id === lastAssistantId && shouldShowThinking ? <ThinkingTrace events={traceEvents} /> : null}
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        <div className="border-t border-gray-200 px-4 py-3 dark:border-gray-700">
          <div className="flex gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Type a message..."
              rows={1}
              className="flex-1 resize-none rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
              disabled={isGenerating}
            />
            <button
              onClick={handleSend}
              disabled={isGenerating || !input.trim()}
              className="rounded-lg bg-blue-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-600 disabled:cursor-not-allowed disabled:opacity-50"
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

  return (
    <div className="mt-1 rounded-md border border-blue-100 bg-blue-50/70 px-2.5 py-2 text-xs dark:border-blue-900/40 dark:bg-blue-950/20">
      <div className="mb-2 flex items-center gap-2 text-blue-600 dark:text-blue-300">
        <Loader2 size={13} className="animate-spin" />
        <span className="font-medium">思考中</span>
        {activeEvent ? <span className="truncate text-blue-400">{activeEvent.label || activeEvent.node}</span> : null}
      </div>
      <div className="space-y-1">
        {visibleEvents.map((event) => (
          <div key={event.id} className="rounded bg-white/70 px-2 py-1.5 dark:bg-gray-900/30">
            <div className="flex items-start gap-2">
              <TraceIcon status={event.status} event={event.event} />
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium text-gray-800 dark:text-gray-100">
                  {event.label || event.node || event.event}
                </div>
                {renderTraceDetail(event)}
                {event.event === "skill_created" ? (
                  <div className="mt-1 rounded bg-emerald-50 px-2 py-1 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-300">
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
  const detail = skillTopic || agentName || supervisorName || model || event.event;
  return <div className="mt-0.5 truncate text-gray-400">{detail}</div>;
}

function TraceIcon({ status, event }: { status: string; event: string }) {
  if (event === "skill_created") return <Wrench size={14} className="mt-0.5 text-emerald-500" />;
  if (status === "running") return <Loader2 size={14} className="mt-0.5 animate-spin text-blue-500" />;
  if (status === "failed") return <XCircle size={14} className="mt-0.5 text-red-500" />;
  if (status === "succeeded") return <CheckCircle2 size={14} className="mt-0.5 text-emerald-500" />;
  return <CheckCircle2 size={14} className="mt-0.5 text-gray-300" />;
}
