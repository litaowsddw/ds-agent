"use client";

import { useState } from "react";
import { CheckCircle2, ChevronDown, ChevronUp, Eye, EyeOff, Loader2, Wrench, XCircle } from "lucide-react";
import type { ChatTraceEvent } from "@/stores/chat";

export default function ThinkingTrace({ events }: { events: ChatTraceEvent[] }) {
  const [expanded, setExpanded] = useState(false);
  const [hidden, setHidden] = useState(false);
  const visibleEvents = events.filter((event) =>
    ["node_started", "node_finished", "skill_created", "error"].includes(event.event)
  );
  const failed = visibleEvents.some((event) => event.status === "failed");
  const activeEvent = failed
    ? undefined
    : [...visibleEvents].reverse().find((event) => event.status === "running");
  const displayEvents = expanded ? visibleEvents : visibleEvents.slice(-5);
  const heading = activeEvent ? "执行中" : failed ? "执行失败" : "执行 Trace";

  if (hidden) {
    return (
      <button
        aria-label="显示执行 Trace"
        className="mb-3 inline-flex items-center gap-1 rounded-lg border border-[#dfe4ee] bg-white px-2.5 py-1.5 text-xs text-[#667085] transition hover:border-[#2f6feb] hover:text-[#2f6feb]"
        onClick={() => setHidden(false)}
        type="button"
      >
        <Eye size={13} />
        显示执行 Trace
      </button>
    );
  }

  return (
    <div className="mb-3 rounded-lg border border-[#dfe4ee] bg-[#f8fafc] px-3 py-2 text-xs">
      <div className={`mb-2 flex items-center gap-2 ${failed && !activeEvent ? "text-red-600" : "text-[#2f6feb]"}`}>
        {activeEvent ? (
          <Loader2 size={13} className="animate-spin" />
        ) : failed ? (
          <XCircle size={13} />
        ) : (
          <CheckCircle2 size={13} className="text-emerald-500" />
        )}
        <span className="font-medium">{heading}</span>
        {activeEvent ? <span className="truncate text-[#667085]">{activeEvent.label || activeEvent.node}</span> : null}
        <button
          aria-label="隐藏执行 Trace"
          className="ml-auto inline-flex shrink-0 items-center gap-1 rounded px-1.5 py-1 text-[#667085] transition hover:bg-white hover:text-[#172033]"
          onClick={() => setHidden(true)}
          title="隐藏执行 Trace"
          type="button"
        >
          <EyeOff size={13} />
          隐藏
        </button>
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
                <TraceDetail event={event} />
                {event.event === "skill_created" ? (
                  <div className="mt-1 rounded bg-emerald-50 px-2 py-1 text-emerald-700">
                    {String(event.data.name || "Skill 已创建")}
                  </div>
                ) : null}
                {event.event === "error" ? (
                  <div className="mt-1 text-red-500">{String(event.data.error || "执行出错")}</div>
                ) : null}
              </div>
            </div>
          </div>
        ))}
      </div>
      {visibleEvents.length > 5 ? (
        <button
          aria-label={expanded ? "收起执行 Trace" : `展开全部 ${visibleEvents.length} 条`}
          className="mt-2 inline-flex items-center gap-1 text-[#2f6feb] hover:underline"
          onClick={() => setExpanded((value) => !value)}
          type="button"
        >
          {expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          {expanded ? "收起" : `展开全部（${visibleEvents.length} 条）`}
        </button>
      ) : null}
    </div>
  );
}

function TraceDetail({ event }: { event: ChatTraceEvent }) {
  const agentName = typeof event.data.agent_name === "string" ? event.data.agent_name : "";
  const supervisorName = typeof event.data.supervisor_name === "string" ? event.data.supervisor_name : "";
  const model = typeof event.data.model_name === "string" ? event.data.model_name : "";
  const skillTopic = typeof event.data.skill_topic === "string" ? event.data.skill_topic : "";
  const workflowRunId = typeof event.data.workflow_run_id === "string" ? event.data.workflow_run_id : "";
  const detail = workflowRunId ? `Run ${workflowRunId}` : skillTopic || agentName || supervisorName || model || event.event;
  return <div className="mt-0.5 truncate text-[#667085]">{detail}</div>;
}

function TraceIcon({ status, event }: { status: ChatTraceEvent["status"]; event: string }) {
  if (event === "skill_created") return <Wrench size={14} className="mt-0.5 text-emerald-500" />;
  if (status === "running") return <Loader2 size={14} className="mt-0.5 animate-spin text-blue-500" />;
  if (status === "failed") return <XCircle size={14} className="mt-0.5 text-red-500" />;
  if (status === "succeeded") return <CheckCircle2 size={14} className="mt-0.5 text-emerald-500" />;
  return <CheckCircle2 size={14} className="mt-0.5 text-gray-300" />;
}
