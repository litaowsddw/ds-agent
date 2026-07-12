"use client";

import { useMemo, useState } from "react";
import RunStatusBadge, { getRunStatusLabel } from "@/components/runs/RunStatusBadge";
import type { WorkflowRun } from "@/types/workflow";

interface RunListProps {
  runs: WorkflowRun[];
  selectedRunId: string;
  onSelect: (run: WorkflowRun) => void;
  workflowLabels?: Record<string, string>;
}

function formatTimestamp(value?: string) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

export default function RunList({
  runs,
  selectedRunId,
  onSelect,
  workflowLabels = {},
}: RunListProps) {
  const [statusFilter, setStatusFilter] = useState("all");
  const statuses = useMemo(
    () => Array.from(new Set(runs.map((run) => run.status).filter(Boolean))).sort(),
    [runs]
  );
  const visibleRuns = statusFilter === "all"
    ? runs
    : runs.filter((run) => run.status === statusFilter);

  return (
    <div className="space-y-3">
      <label className="block text-xs font-medium text-[#475467]">
        <span className="sr-only">按状态筛选运行</span>
        <select
          aria-label="按状态筛选运行"
          className="w-full rounded-lg border border-[#d0d5dd] bg-white px-3 py-2 text-sm text-[#344054]"
          onChange={(event) => setStatusFilter(event.target.value)}
          value={statusFilter}
        >
          <option value="all">全部状态</option>
          {statuses.map((status) => (
            <option key={status} value={status}>{getRunStatusLabel(status)}</option>
          ))}
        </select>
      </label>

      {visibleRuns.length === 0 ? (
        <p className="py-5 text-center text-xs text-[#667085]">没有匹配的运行记录。</p>
      ) : null}
      {visibleRuns.map((run) => {
        const workflowLabel = workflowLabels[run.workflow_id] || run.workflow_id || "—";
        return (
          <button
            aria-pressed={selectedRunId === run.run_id}
            className={`w-full rounded-lg border p-3 text-left text-sm transition ${
              selectedRunId === run.run_id
                ? "border-[#2f6feb] bg-[#eef4ff]"
                : "border-[#dfe4ee] bg-white hover:border-[#93c5fd]"
            }`}
            key={run.run_id}
            onClick={() => onSelect(run)}
            type="button"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate font-mono text-xs text-[#172033]">{run.run_id || "—"}</div>
                <div className="mt-1 truncate text-xs text-[#475467]">工作流 {workflowLabel}</div>
              </div>
              <RunStatusBadge status={run.status} />
            </div>
            <div className="mt-2 text-xs text-[#667085]">{formatTimestamp(run.created_at)}</div>
          </button>
        );
      })}
    </div>
  );
}
