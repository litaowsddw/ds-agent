"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { BarChart3, RefreshCw } from "lucide-react";
import Panel from "@/components/ui/Panel";
import { EmptyText, Metric } from "@/components/ui/DataDisplay";
import { SelectInput, TextInput } from "@/components/ui/Form";
import { SecondaryButton } from "@/components/ui/Button";
import {
  getUsageEvents,
  getUsageSummary,
  type UsageAggregate,
  type UsageEvent,
  type UsageQueryFilters,
} from "@/lib/api";

const DAYS_SEVEN_MS = 7 * 24 * 60 * 60 * 1000;

function token(value: number | null | undefined) {
  return value === null || value === undefined ? "Provider 未提供用量" : `${value} Token`;
}

function percentage(value: number | null) {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

function percentile(values: number[], ratio: number) {
  if (values.length === 0) return null;
  const sorted = [...values].sort((left, right) => left - right);
  return sorted[Math.min(sorted.length - 1, Math.ceil(sorted.length * ratio) - 1)];
}

function qualityLabel(group: UsageAggregate) {
  if (group.unknown_usage_calls > 0 || group.total_tokens === null || group.total_tokens === undefined) return "未知";
  return "真实";
}

function platformCacheLabel(events: UsageEvent[]) {
  const known = events.filter((event) => event.prefix_cache_status !== null && event.prefix_cache_status !== undefined);
  if (known.length === 0) return "不支持";
  const eligible = known.filter((event) => event.prefix_cache_status === "eligible").length;
  return percentage(eligible / known.length);
}

function InsightsContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const initialAgent = searchParams.get("agent") ?? "";
  const [agentId, setAgentId] = useState(initialAgent);
  const [model, setModel] = useState("");
  const [apiName, setApiName] = useState("");
  const [workflowId, setWorkflowId] = useState("");
  const [source, setSource] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [cacheStatusFilter, setCacheStatusFilter] = useState("all");
  const [qualityFilter, setQualityFilter] = useState("all");
  const [groups, setGroups] = useState<UsageAggregate[]>([]);
  const [events, setEvents] = useState<UsageEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshToken, setRefreshToken] = useState(0);

  const filters = useMemo<UsageQueryFilters>(() => {
    const to = new Date();
    const from = new Date(to.getTime() - DAYS_SEVEN_MS);
    return {
      from: from.toISOString(),
      to: to.toISOString(),
      agent_id: agentId || undefined,
      model: model || undefined,
      api_name: apiName || undefined,
      workflow_id: workflowId || undefined,
      source: source || undefined,
      group_by: "model",
      granularity: "day",
      limit: 200,
    };
  }, [agentId, apiName, model, source, workflowId]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    void Promise.all([getUsageSummary(filters), getUsageEvents(filters)])
      .then(([summary, eventResponse]) => {
        if (!active) return;
        setGroups(summary.groups);
        setEvents(eventResponse.events);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "无法加载用量洞察。");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [filters, refreshToken]);

  const filteredEvents = useMemo(() => events.filter((event) => {
    if (statusFilter !== "all" && event.dispatch_status !== statusFilter) return false;
    if (cacheStatusFilter !== "all" && event.cache_usage_status !== cacheStatusFilter) return false;
    if (qualityFilter === "unknown" && event.usage_status !== "unavailable") return false;
    if (qualityFilter === "real" && event.usage_status === "unavailable") return false;
    return true;
  }), [cacheStatusFilter, events, qualityFilter, statusFilter]);
  const callCount = groups.reduce((total, group) => total + group.call_count, 0);
  const unknownCalls = groups.reduce((total, group) => total + group.unknown_usage_calls, 0);
  const sumKnown = (field: "input_tokens" | "output_tokens" | "total_tokens" | "cache_read_input_tokens") => {
    const values = groups.map((group) => group[field]).filter((value): value is number => value !== null && value !== undefined);
    return values.length ? values.reduce((total, value) => total + value, 0) : null;
  };
  const latencyValues = filteredEvents.map((event) => event.latency_ms).filter((value): value is number => value !== null && value !== undefined);
  const successful = filteredEvents.filter((event) => event.dispatch_status === "succeeded" || event.dispatch_status === "completed").length;
  const successRate = filteredEvents.length ? successful / filteredEvents.length : null;

  function updateAgent(value: string) {
    setAgentId(value);
    const params = new URLSearchParams(searchParams.toString());
    if (value) params.set("agent", value);
    else params.delete("agent");
    router.replace(`/insights${params.size ? `?${params.toString()}` : ""}`);
  }

  return (
    <div className="space-y-6">
      <header className="rounded-lg border border-[#dfe4ee] bg-white px-5 py-4">
        <h2 className="text-base font-semibold text-[#172033]">用量洞察</h2>
        <p className="mt-1 text-xs text-[#667085]">默认展示最近 7 天的 Provider 实际用量；未知数据不会按 0 计算。</p>
      </header>

      <Panel title="筛选条件" icon={<BarChart3 size={17} />} actions={<SecondaryButton label="刷新" onClick={() => setRefreshToken((value) => value + 1)} />}>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <TextInput label="Agent ID" value={agentId} onChange={updateAgent} placeholder="保留 URL 中的 agent 筛选" />
          <TextInput label="模型" value={model} onChange={setModel} placeholder="例如 gpt-4o" />
          <TextInput label="API" value={apiName} onChange={setApiName} placeholder="例如 chat.completions" />
          <TextInput label="Workflow ID" value={workflowId} onChange={setWorkflowId} />
          <TextInput label="来源" value={source} onChange={setSource} placeholder="例如 workflow_node" />
          <SelectInput label="调用状态" value={statusFilter} onChange={setStatusFilter} options={[{ label: "全部", value: "all" }, { label: "成功", value: "succeeded" }, { label: "失败", value: "failed" }]} />
          <SelectInput label="Provider 缓存状态" value={cacheStatusFilter} onChange={setCacheStatusFilter} options={[{ label: "全部", value: "all" }, { label: "已知", value: "known" }, { label: "未知", value: "unknown" }]} />
          <SelectInput label="数据质量" value={qualityFilter} onChange={setQualityFilter} options={[{ label: "全部", value: "all" }, { label: "真实", value: "real" }, { label: "未知", value: "unknown" }]} />
        </div>
      </Panel>

      {error ? <p className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
      {loading ? <p className="text-sm text-[#667085]">正在加载用量洞察…</p> : null}

      {!loading && !error ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Metric label="调用次数" value={callCount} />
            <Metric label="输入 Token" value={token(sumKnown("input_tokens"))} />
            <Metric label="输出 Token" value={token(sumKnown("output_tokens"))} />
            <Metric label="总 Token" value={token(sumKnown("total_tokens"))} />
            <Metric label="成功率（最近事件）" value={percentage(successRate)} />
            <Metric label="P50 延迟（最近事件）" value={percentile(latencyValues, 0.5) === null ? "—" : `${percentile(latencyValues, 0.5)} ms`} />
            <Metric label="P95 延迟（最近事件）" value={percentile(latencyValues, 0.95) === null ? "—" : `${percentile(latencyValues, 0.95)} ms`} />
            <Metric label="Provider 缓存命中 Token" value={token(sumKnown("cache_read_input_tokens"))} />
            <Metric label="Provider 缓存数据覆盖" value={groups.some((group) => group.cache_read_input_tokens !== null && group.cache_read_input_tokens !== undefined) ? "已知" : "未知"} />
            <Metric label="平台缓存命中率" value={platformCacheLabel(filteredEvents)} />
          </div>

          <Panel title="按模型汇总" icon={<RefreshCw size={17} />}>
            {groups.length === 0 ? <EmptyText text="当前筛选条件下没有用量事件。" /> : null}
            <div className="space-y-2">
              {groups.map((group, index) => (
                <div key={`${group.model ?? "unknown"}-${group.bucket_start ?? index}`} className="grid gap-2 rounded-lg border border-[#dfe4ee] bg-[#f8fafc] p-3 text-sm md:grid-cols-[minmax(0,1fr)_auto_auto_auto]">
                  <div className="min-w-0">
                    <div className="truncate font-medium text-[#172033]">{group.model ?? "未命名模型"}</div>
                    <div className="mt-1 text-xs text-[#667085]">{group.call_count} 次调用 · {group.unknown_usage_calls} 次未知</div>
                  </div>
                  <span className="text-[#344054]">{token(group.total_tokens)}</span>
                  <span className="rounded-full bg-white px-2 py-1 text-xs text-[#344054]">{qualityLabel(group)}</span>
                  {group.estimated_total_cost !== null && group.estimated_total_cost !== undefined ? (
                    <span className="text-xs text-[#667085]">估算 {group.currency ?? ""} {group.estimated_total_cost}</span>
                  ) : <span className="text-xs text-[#667085]">未提供估算成本</span>}
                </div>
              ))}
            </div>
          </Panel>
          {unknownCalls ? <p className="text-xs text-[#667085]">共有 {unknownCalls} 次调用标记为未知：Provider 未提供用量。</p> : null}
        </>
      ) : null}
    </div>
  );
}

export default function InsightsPage() {
  return (
    <Suspense fallback={<p className="text-sm text-[#667085]">正在加载用量洞察…</p>}>
      <InsightsContent />
    </Suspense>
  );
}
