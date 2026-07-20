/** 运行历史页面。

查看 Workflow 运行历史、运行详情和节点日志。
 */

"use client";

import { useCallback, useEffect, useMemo } from "react";
import { Activity, CheckCircle2, FileText, GitBranch, RefreshCw } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useWorkflowStore } from "@/stores/workflow";
import Panel from "@/components/ui/Panel";
import { EmptyText } from "@/components/ui/DataDisplay";
import AgentRequired from "@/components/ui/AgentRequired";
import WorkspaceRequired from "@/components/ui/WorkspaceRequired";
import NodeRunCard from "@/components/runs/NodeRunCard";
import RunList from "@/components/runs/RunList";
import RunSummary from "@/components/runs/RunSummary";

export default function RunsPage() {
  const workspace = useWorkspaceStore((s) => s.workspace);
  const agents = useWorkspaceStore((s) => s.agents);
  const selectedAgentId = useWorkspaceStore((s) => s.selectedAgentId);
  const runs = useWorkflowStore((s) => s.runs);
  const selectedRunId = useWorkflowStore((s) => s.selectedRunId);
  const nodeRuns = useWorkflowStore((s) => s.nodeRuns);
  const versions = useWorkflowStore((s) => s.versions);
  const workflows = useWorkflowStore((s) => s.workflows);
  const loadNodeRuns = useWorkflowStore((s) => s.loadNodeRuns);
  const setSelectedRunId = useWorkflowStore((s) => s.setSelectedRunId);
  const clearRunSelection = useWorkflowStore((s) => s.clearRunSelection);
  const refreshRuns = useWorkflowStore((s) => s.refreshRuns);
  const refreshWorkflows = useWorkflowStore((s) => s.refreshWorkflows);

  const selectedAgent = agents.find((agent) => agent.agent_id === selectedAgentId) ?? null;
  const agentRuns = useMemo(
    () => (selectedAgentId ? runs.filter((run) => run.agent_id === selectedAgentId) : []),
    [runs, selectedAgentId]
  );
  const selectedRun = agentRuns.find((r) => r.run_id === selectedRunId) ?? null;
  const isActiveRun = selectedRun?.status === "pending" || selectedRun?.status === "running";
  const workflowLabels = useMemo(
    () => Object.fromEntries(workflows.map((workflow) => [workflow.workflow_id, workflow.name])),
    [workflows]
  );

  useEffect(() => {
    if (workspace && selectedAgentId) {
      void refreshRuns(workspace.orgId, workspace.userId);
      void refreshWorkflows(workspace.orgId, workspace.userId, selectedAgentId);
    }
  }, [workspace, selectedAgentId, refreshRuns, refreshWorkflows]);

  useEffect(() => {
    if (!selectedRunId) return;
    const selectedRunBelongsToAgent = agentRuns.some((run) => run.run_id === selectedRunId);
    if (!selectedRunBelongsToAgent) {
      clearRunSelection();
    }
  }, [agentRuns, selectedRunId, clearRunSelection]);

  const refreshSelectedRun = useCallback(async () => {
    if (!workspace || !selectedRunId) return;
    await refreshRuns(workspace.orgId, workspace.userId);
    await loadNodeRuns(selectedRunId, workspace.userId);
  }, [loadNodeRuns, refreshRuns, selectedRunId, workspace]);

  useEffect(() => {
    if (!workspace || !selectedRunId || !selectedRun) return;
    void loadNodeRuns(selectedRunId, workspace.userId).catch(() => undefined);
  }, [loadNodeRuns, selectedRun?.run_id, selectedRunId, workspace]);

  useEffect(() => {
    if (!isActiveRun) return;
    const intervalId = window.setInterval(() => {
      void refreshSelectedRun().catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(intervalId);
  }, [isActiveRun, refreshSelectedRun]);

  if (!workspace) {
    return <WorkspaceRequired />;
  }

  if (!selectedAgent) {
    return <AgentRequired description="请先选择或创建一个 Agent，再查看它的运行记录。" />;
  }

  return (
    <div className="space-y-6">
      <header className="rounded-lg border border-[#dfe4ee] bg-white px-5 py-4">
        <div className="text-sm font-semibold text-[#172033]">Agent 运行记录</div>
        <div className="mt-1 text-xs text-[#667085]">
          {selectedAgent.name} · {agentRuns.length} 次运行
        </div>
      </header>

      <div className="grid gap-6 xl:grid-cols-[360px_1fr]">
        {/* 运行历史列表 */}
        <Panel title="运行历史" icon={<Activity size={17} />}>
          {agentRuns.length === 0 ? (
            <EmptyText text={`${selectedAgent.name} 暂无运行记录。请先发布并运行它的 Workflow。`} />
          ) : (
            <RunList
              onSelect={(run) => {
                setSelectedRunId(run.run_id);
              }}
              runs={agentRuns}
              selectedRunId={selectedRunId}
              workflowLabels={workflowLabels}
            />
          )}
        </Panel>

        {/* 运行详情 */}
        <div className="space-y-6">
          <Panel title="运行详情" icon={<CheckCircle2 size={17} />}>
            {selectedRun ? (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[#dfe4ee] bg-[#f8fafc] px-3 py-2">
                  <p aria-live="polite" className="text-xs text-[#667085]">
                    {isActiveRun ? "运行仍在进行中，节点详情每 3 秒自动刷新。" : "已加载该次运行的输入、输出和节点轨迹。"}
                  </p>
                  <button
                    className="inline-flex items-center gap-1 rounded-md border border-[#d0d5dd] bg-white px-2.5 py-1.5 text-xs font-medium text-[#344054] hover:bg-[#f9fafb]"
                    onClick={() => void refreshSelectedRun().catch(() => undefined)}
                    type="button"
                  >
                    <RefreshCw aria-hidden="true" size={14} />
                    刷新详情
                  </button>
                </div>
                <RunSummary
                  run={selectedRun}
                  workflowLabel={workflowLabels[selectedRun.workflow_id]}
                />
              </div>
            ) : (
              <EmptyText text="选择当前 Agent 的一次运行后查看输出。" />
            )}
          </Panel>

          <Panel title="节点日志" icon={<GitBranch size={17} />}>
            {nodeRuns.length > 0 ? (
              <div className="grid gap-2 md:grid-cols-2">
                {nodeRuns.map((nodeRun) => (
                  <NodeRunCard key={nodeRun.node_run_id} nodeRun={nodeRun} />
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
