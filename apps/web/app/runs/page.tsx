/** 运行历史页面。

查看 Workflow 运行历史、运行详情和节点日志。
 */

"use client";

import { useEffect, useMemo } from "react";
import { Activity, CheckCircle2, FileText, GitBranch } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useWorkflowStore } from "@/stores/workflow";
import Panel from "@/components/ui/Panel";
import { EmptyText } from "@/components/ui/DataDisplay";
import WorkspaceRequired from "@/components/ui/WorkspaceRequired";

export default function RunsPage() {
  const workspace = useWorkspaceStore((s) => s.workspace);
  const agents = useWorkspaceStore((s) => s.agents);
  const selectedAgentId = useWorkspaceStore((s) => s.selectedAgentId);
  const runs = useWorkflowStore((s) => s.runs);
  const selectedRunId = useWorkflowStore((s) => s.selectedRunId);
  const nodeRuns = useWorkflowStore((s) => s.nodeRuns);
  const versions = useWorkflowStore((s) => s.versions);
  const loadNodeRuns = useWorkflowStore((s) => s.loadNodeRuns);
  const clearRunSelection = useWorkflowStore((s) => s.clearRunSelection);
  const refreshRuns = useWorkflowStore((s) => s.refreshRuns);

  const selectedAgent = agents.find((agent) => agent.agent_id === selectedAgentId) ?? null;
  const agentRuns = useMemo(
    () => (selectedAgentId ? runs.filter((run) => run.agent_id === selectedAgentId) : []),
    [runs, selectedAgentId]
  );
  const selectedRun = agentRuns.find((r) => r.run_id === selectedRunId) ?? null;

  useEffect(() => {
    if (workspace) {
      void refreshRuns(workspace.orgId, workspace.userId);
    }
  }, [workspace, refreshRuns]);

  useEffect(() => {
    if (!selectedRunId) return;
    const selectedRunBelongsToAgent = agentRuns.some((run) => run.run_id === selectedRunId);
    if (!selectedRunBelongsToAgent) {
      clearRunSelection();
    }
  }, [agentRuns, selectedRunId, clearRunSelection]);

  if (!workspace) {
    return <WorkspaceRequired />;
  }

  if (!selectedAgentId) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-[#667085]">
        请先在 Agents 中选择或创建一个 Agent，再查看它的运行记录。
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header className="rounded-lg border border-[#dfe4ee] bg-white px-5 py-4">
        <div className="text-sm font-semibold text-[#172033]">Agent Runs</div>
        <div className="mt-1 text-xs text-[#667085]">
          {selectedAgent ? selectedAgent.name : "Selected Agent"} · {agentRuns.length} runs
        </div>
      </header>

      <div className="grid gap-6 xl:grid-cols-[360px_1fr]">
        {/* 运行历史列表 */}
        <Panel title="运行历史" icon={<Activity size={17} />}>
          <div className="space-y-2">
            {agentRuns.length === 0 ? (
              <EmptyText text={`${selectedAgent ? selectedAgent.name : "当前 Agent"} 暂无运行记录。请先发布并运行它的 Workflow。`} />
            ) : null}
            {agentRuns.map((run) => (
              <button
                key={run.run_id}
                className={`w-full rounded-lg border p-3 text-left text-sm transition ${
                  selectedRunId === run.run_id
                    ? "border-[#2f6feb] bg-[#eef4ff]"
                    : "border-[#dfe4ee] bg-white hover:border-[#93c5fd]"
                }`}
                onClick={() => {
                  void loadNodeRuns(run.run_id, workspace.userId);
                }}
                type="button"
              >
                <div className="font-mono text-xs text-[#172033]">{run.run_id}</div>
                <div className="mt-1 text-xs text-[#667085]">状态：{run.status}</div>
              </button>
            ))}
          </div>
        </Panel>

        {/* 运行详情 */}
        <div className="space-y-6">
          <Panel title="运行详情" icon={<CheckCircle2 size={17} />}>
            {selectedRun ? (
              <pre className="max-h-[320px] overflow-auto rounded-lg bg-[#0f172a] p-3 text-xs leading-5 text-[#dbeafe]">
                {JSON.stringify(selectedRun.output_data, null, 2)}
              </pre>
            ) : (
              <EmptyText text="选择当前 Agent 的一次运行后查看输出。" />
            )}
          </Panel>

          <Panel title="节点日志" icon={<GitBranch size={17} />}>
            {nodeRuns.length > 0 ? (
              <div className="grid gap-2 md:grid-cols-2">
                {nodeRuns.map((nodeRun) => (
                  <div
                    key={nodeRun.node_run_id}
                    className="rounded-lg border border-[#dfe4ee] bg-white p-3 text-sm"
                  >
                    <div className="font-medium text-[#172033]">{nodeRun.node_id}</div>
                    <div className="mt-2 text-xs text-[#667085]">
                      {nodeRun.node_type} / {nodeRun.status} / {nodeRun.elapsed_ms}ms
                    </div>
                    {nodeRun.error_message && (
                      <div className="mt-2 rounded-lg bg-[#fff1f0] p-2 text-xs leading-5 text-[#b42318]">
                        {nodeRun.error_message}
                      </div>
                    )}
                    <pre className="mt-2 max-h-[220px] overflow-auto rounded-lg bg-[#0f172a] p-2 text-xs leading-5 text-[#dbeafe]">
                      {JSON.stringify(nodeRun.output_data, null, 2)}
                    </pre>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyText text="选择当前 Agent 的一次运行后查看节点日志。" />
            )}
          </Panel>

          <Panel title="发布版本" icon={<FileText size={17} />}>
            {versions.length > 0 ? (
              <div className="space-y-2">
                {versions.map((version) => (
                  <div
                    key={version.version_id}
                    className="rounded-lg border border-[#dfe4ee] bg-[#f8fafc] px-3 py-2 text-sm text-[#344054]"
                  >
                    v{version.version_number} · {version.version_id}
                  </div>
                ))}
              </div>
            ) : (
              <EmptyText text="暂无发布版本。" />
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}
