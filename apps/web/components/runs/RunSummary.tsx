import { useEffect, useMemo, useState } from "react";
import JsonDisclosure from "@/components/runs/JsonDisclosure";
import RunStatusBadge from "@/components/runs/RunStatusBadge";
import { getUsageEvents, type UsageEvent } from "@/lib/api";
import type { WorkflowRun } from "@/types/workflow";

export interface RunUsageSummary {
  callCount: number;
  unknownUsageCalls: number;
  inputTokens: number | null;
  outputTokens: number | null;
  totalTokens: number | null;
  providerCacheReadTokens: number | null;
}

interface RunSummaryProps {
  run: WorkflowRun;
  workflowLabel?: string;
  usage?: RunUsageSummary;
}

function displayValue(value?: string | null) {
  return value?.trim() || "—";
}

function displayTime(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString("zh-CN");
}

function tokenValue(value: number | null | undefined) {
  return value === null || value === undefined ? "Provider 未提供用量" : `${value} Token`;
}

function summarizeUsage(events: UsageEvent[]): RunUsageSummary | null {
  if (events.length === 0) return null;
  const sum = (field: "input_tokens" | "output_tokens" | "total_tokens" | "cache_read_input_tokens") => {
    const values = events.map((event) => event[field]).filter((value): value is number => value !== null && value !== undefined);
    return values.length ? values.reduce((total, value) => total + value, 0) : null;
  };
  return {
    callCount: events.length,
    unknownUsageCalls: events.filter((event) => event.usage_status === "unavailable").length,
    inputTokens: sum("input_tokens"),
    outputTokens: sum("output_tokens"),
    totalTokens: sum("total_tokens"),
    providerCacheReadTokens: sum("cache_read_input_tokens"),
  };
}

export default function RunSummary({ run, workflowLabel, usage: suppliedUsage }: RunSummaryProps) {
  const [loadedEvents, setLoadedEvents] = useState<UsageEvent[] | null>(null);
  const [usageIncomplete, setUsageIncomplete] = useState(false);
  const usage = useMemo(
    () => suppliedUsage ?? (usageIncomplete ? null : loadedEvents ? summarizeUsage(loadedEvents) : null),
    [loadedEvents, suppliedUsage, usageIncomplete]
  );

  useEffect(() => {
    if (suppliedUsage) return;
    let active = true;
    setUsageIncomplete(false);
    void getUsageEvents({ workflow_run_id: run.run_id, limit: 200 })
      .then((response) => {
        if (active) {
          setUsageIncomplete(response.has_more);
          setLoadedEvents(response.events);
        }
      })
      .catch(() => {
        if (active) {
          setUsageIncomplete(false);
          setLoadedEvents([]);
        }
      });
    return () => {
      active = false;
    };
  }, [run.run_id, suppliedUsage]);

  return (
    <div className="space-y-4">
      {run.error_message ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700" role="alert">
          <div className="font-medium">运行失败</div>
          <div className="mt-1 break-words text-xs leading-5">{run.error_message}</div>
        </div>
      ) : null}

      <div className="grid gap-3 rounded-lg border border-[#dfe4ee] bg-white p-4 sm:grid-cols-2 lg:grid-cols-3">
        <SummaryField label="状态"><RunStatusBadge status={run.status} /></SummaryField>
        <SummaryField label="Workflow">{displayValue(workflowLabel || run.workflow_id)}</SummaryField>
        <SummaryField label="版本">{displayValue(run.version_id)}</SummaryField>
        <SummaryField label="运行 ID">{displayValue(run.run_id)}</SummaryField>
        <SummaryField label="创建时间">{displayTime(run.created_at)}</SummaryField>
        <SummaryField label="更新时间">{displayTime(run.updated_at)}</SummaryField>
      </div>

      <div className="rounded-lg border border-[#dfe4ee] bg-[#f8fafc] p-4">
        <div className="mb-3 text-sm font-semibold text-[#172033]">运行用量</div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <SummaryField label="调用次数">{usage ? String(usage.callCount) : "—"}</SummaryField>
          <SummaryField label="总 Token">{usage ? tokenValue(usage.totalTokens) : usageIncomplete ? "用量不完整" : "—"}</SummaryField>
          <SummaryField label="Provider 缓存命中 Token">
            {usage ? tokenValue(usage.providerCacheReadTokens) : "—"}
          </SummaryField>
          <SummaryField label="平台缓存命中率">不支持</SummaryField>
        </div>
        {usage?.unknownUsageCalls ? (
          <p className="mt-3 text-xs text-[#667085]">{usage.unknownUsageCalls} 次调用的 Provider 未提供用量。</p>
        ) : null}
        {usageIncomplete ? (
          <p className="mt-3 text-xs text-[#667085]">运行事件超过可显示上限，无法汇总完整用量。</p>
        ) : null}
      </div>

      <JsonDisclosure label="输出" value={run.output_data} />
    </div>
  );
}

function SummaryField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="text-xs text-[#667085]">{label}</div>
      <div className="mt-1 break-words text-sm font-medium text-[#172033]">{children}</div>
    </div>
  );
}
