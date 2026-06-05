/** MCP tool registry and authorization page. */

"use client";

import { useEffect } from "react";
import { PlugZap, Server, ShieldCheck } from "lucide-react";
import { useRuntimeStore } from "@/stores/runtime";
import { useWorkspaceStore } from "@/stores/workspace";
import { showToast } from "@/components/layout/AppLayout";
import Panel from "@/components/ui/Panel";
import { TextInput } from "@/components/ui/Form";
import { PrimaryButton } from "@/components/ui/Button";
import { EmptyText, Metric } from "@/components/ui/DataDisplay";

export default function ToolsPage() {
  const workspace = useWorkspaceStore((s) => s.workspace);
  const selectedAgentId = useWorkspaceStore((s) => s.selectedAgentId);
  const busy = useWorkspaceStore((s) => s.busy);

  const mcpForm = useRuntimeStore((s) => s.mcpForm);
  const mcpServers = useRuntimeStore((s) => s.mcpServers);
  const mcpTools = useRuntimeStore((s) => s.mcpTools);
  const setMcpForm = useRuntimeStore((s) => s.setMcpForm);
  const createMcpTool = useRuntimeStore((s) => s.createMcpTool);
  const refreshRuntimeData = useRuntimeStore((s) => s.refreshRuntimeData);

  useEffect(() => {
    if (workspace) {
      void refreshRuntimeData(workspace.orgId, workspace.userId, selectedAgentId || undefined);
    }
  }, [workspace, selectedAgentId, refreshRuntimeData]);

  if (!workspace) {
    return <div className="flex h-64 items-center justify-center text-sm text-[#667085]">请先创建工作空间</div>;
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[420px_1fr]">
      <Panel title="注册 MCP Server" icon={<Server size={17} />}>
        <div className="space-y-3">
          <TextInput label="Server 名称" value={mcpForm.serverName} onChange={(serverName) => setMcpForm({ ...mcpForm, serverName })} />
          <TextInput label="Server URL" value={mcpForm.url} onChange={(url) => setMcpForm({ ...mcpForm, url })} />
          <TextInput label="Tool 名称" value={mcpForm.toolName} onChange={(toolName) => setMcpForm({ ...mcpForm, toolName })} />
          <PrimaryButton
            busy={busy}
            label="创建并授权给当前 Agent"
            onClick={async () => {
              try {
                if (!selectedAgentId) throw new Error("请先创建或选择 Agent");
                await createMcpTool(workspace.userId, workspace.orgId, selectedAgentId);
                await refreshRuntimeData(workspace.orgId, workspace.userId, selectedAgentId);
                showToast("success", "MCP Tool 已创建并授权");
              } catch (error) {
                showToast("error", error instanceof Error ? error.message : "创建 MCP Tool 失败");
              }
            }}
          />
        </div>
      </Panel>

      <div className="space-y-6">
        <Panel title="工具授权概览" icon={<ShieldCheck size={17} />}>
          <div className="grid grid-cols-3 gap-3">
            <Metric label="Servers" value={mcpServers.length} />
            <Metric label="Authorized Tools" value={mcpTools.length} />
            <Metric label="Agent" value={selectedAgentId ? selectedAgentId.slice(0, 8) : "未选择"} />
          </div>
        </Panel>

        <Panel title="MCP Servers" icon={<Server size={17} />}>
          <div className="space-y-2">
            {mcpServers.length === 0 ? <EmptyText text="暂无 MCP Server" /> : null}
            {mcpServers.map((server) => (
              <div key={server.server_id} className="rounded-lg border border-[#dfe4ee] bg-white p-3 text-sm">
                <div className="font-medium text-[#172033]">{server.name}</div>
                <div className="mt-1 text-xs text-[#667085]">{server.transport} · {server.url}</div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="当前 Agent 可调用工具" icon={<PlugZap size={17} />}>
          <div className="space-y-2">
            {mcpTools.length === 0 ? <EmptyText text="暂无已授权工具；创建后可在 Workflow 的 Tool 节点中选择" /> : null}
            {mcpTools.map((tool) => (
              <div key={tool.tool_id} className="rounded-lg border border-[#dfe4ee] bg-[#f8fafc] p-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-[#172033]">{tool.name}</span>
                  <span className="rounded-full bg-[#eef4ff] px-2 py-1 text-xs text-[#2f6feb]">{tool.risk_level}</span>
                </div>
                <div className="mt-1 text-xs text-[#667085]">{tool.description || tool.tool_id}</div>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
