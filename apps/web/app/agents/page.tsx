/** Agent management page backed by real API data. */

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Bot, FileText, Network, Save, Settings } from "lucide-react";
import { showToast } from "@/components/layout/AppLayout";
import { PrimaryButton } from "@/components/ui/Button";
import { EmptyText, Metric } from "@/components/ui/DataDisplay";
import { SelectInput, TextArea, TextInput } from "@/components/ui/Form";
import Panel from "@/components/ui/Panel";
import WorkspaceRequired from "@/components/ui/WorkspaceRequired";
import { apiRequest } from "@/lib/api";
import { useRuntimeStore } from "@/stores/runtime";
import { useWorkflowStore } from "@/stores/workflow";
import { useWorkspaceStore } from "@/stores/workspace";

export default function AgentsPage() {
  const workspace = useWorkspaceStore((state) => state.workspace);
  const agents = useWorkspaceStore((state) => state.agents);
  const selectedAgentId = useWorkspaceStore((state) => state.selectedAgentId);
  const busy = useWorkspaceStore((state) => state.busy);
  const setSelectedAgentId = useWorkspaceStore((state) => state.setSelectedAgentId);
  const createAgent = useWorkspaceStore((state) => state.createAgent);
  const updateAgent = useWorkspaceStore((state) => state.updateAgent);
  const refreshAgents = useWorkspaceStore((state) => state.refreshAgents);
  const getSelectedAgent = useWorkspaceStore((state) => state.getSelectedAgent);

  const skills = useRuntimeStore((state) => state.skills);
  const mcpTools = useRuntimeStore((state) => state.mcpTools);
  const memories = useRuntimeStore((state) => state.memories);
  const sessions = useRuntimeStore((state) => state.sessions);
  const modelProviders = useRuntimeStore((state) => state.modelProviders);
  const refreshRuntimeData = useRuntimeStore((state) => state.refreshRuntimeData);
  const workflows = useWorkflowStore((state) => state.workflows);
  const refreshWorkflows = useWorkflowStore((state) => state.refreshWorkflows);

  const [agentForm, setAgentForm] = useState({
    name: "",
    description: "",
    modelProvider: "",
    modelName: "",
    systemPrompt: "",
    temperature: "0.3",
    maxTokens: "",
    contextTokenLimit: "",
    defaultWorkflowId: "",
  });
  const [parameterForm, setParameterForm] = useState({
    name: "",
    description: "",
    modelProvider: "",
    modelName: "",
    systemPrompt: "",
    temperature: "0.3",
    maxTokens: "",
    contextTokenLimit: "",
    defaultWorkflowId: "",
  });
  const [workspaceText, setWorkspaceText] = useState("");
  const selectedAgent = getSelectedAgent();
  const selectedProvider = modelProviders.find((provider) => provider.provider_key === agentForm.modelProvider);
  const modelOptions = selectedProvider?.models ?? [];
  const parameterProvider = modelProviders.find((provider) => provider.provider_key === parameterForm.modelProvider);
  const parameterModelOptions = parameterProvider?.models ?? [];

  useEffect(() => {
    if (!workspace) return;
    void refreshAgents();
    void refreshRuntimeData(workspace.orgId, workspace.userId);
  }, [workspace, refreshAgents, refreshRuntimeData]);

  useEffect(() => {
    if (!workspace || !selectedAgentId) return;
    void refreshRuntimeData(workspace.orgId, workspace.userId, selectedAgentId);
    void refreshWorkflows(workspace.orgId, workspace.userId, selectedAgentId);
  }, [workspace, selectedAgentId, refreshRuntimeData, refreshWorkflows]);

  useEffect(() => {
    if (!selectedAgent) {
      setParameterForm({
        name: "",
        description: "",
        modelProvider: "",
        modelName: "",
        systemPrompt: "",
        temperature: "0.3",
        maxTokens: "",
        contextTokenLimit: "",
        defaultWorkflowId: "",
      });
      return;
    }
    setParameterForm({
      name: selectedAgent.name,
      description: selectedAgent.description ?? "",
      modelProvider: selectedAgent.model_provider ?? "",
      modelName: selectedAgent.model_name ?? "",
      systemPrompt: selectedAgent.system_prompt ?? "",
      temperature: String(selectedAgent.temperature ?? 0.3),
      maxTokens: selectedAgent.max_tokens ? String(selectedAgent.max_tokens) : "",
      contextTokenLimit: selectedAgent.context_token_limit ? String(selectedAgent.context_token_limit) : "",
      defaultWorkflowId: selectedAgent.default_workflow_id ?? "",
    });
  }, [selectedAgent]);

  if (!workspace) {
    return <WorkspaceRequired />;
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[360px_1fr]">
      <div className="space-y-6">
        <Panel title="创建 Agent" icon={<Bot size={17} />}>
          <div className="space-y-3">
            <TextInput label="名称" placeholder="输入 Agent 名称" value={agentForm.name} onChange={(name) => setAgentForm({ ...agentForm, name })} />
            <TextArea label="描述" placeholder="描述这个 Agent 的职责" rows={4} value={agentForm.description} onChange={(description) => setAgentForm({ ...agentForm, description })} />
            <SelectInput
              label="模型供应商"
              value={agentForm.modelProvider}
              onChange={(modelProvider) =>
                setAgentForm({
                  ...agentForm,
                  modelProvider,
                  modelName: modelProviders.find((provider) => provider.provider_key === modelProvider)?.default_model ?? "",
                })
              }
              options={[
                { label: "暂不绑定默认模型", value: "" },
                ...modelProviders.map((provider) => ({ label: provider.display_name, value: provider.provider_key })),
              ]}
            />
            <SelectInput
              label="默认模型"
              value={agentForm.modelName}
              onChange={(modelName) => setAgentForm({ ...agentForm, modelName })}
              options={
                modelOptions.length > 0
                  ? modelOptions.map((model) => ({ label: model, value: model }))
                  : [{ label: "请先选择模型供应商", value: "" }]
              }
            />
            <TextArea
              label="系统提示词"
              placeholder="定义 Agent 的角色、边界和输出要求"
              rows={4}
              value={agentForm.systemPrompt}
              onChange={(systemPrompt) => setAgentForm({ ...agentForm, systemPrompt })}
            />
            <TextInput
              label="上下文压缩上限（tokens）"
              type="number"
              placeholder="默认 2400，最小 800"
              value={agentForm.contextTokenLimit}
              onChange={(contextTokenLimit) => setAgentForm({ ...agentForm, contextTokenLimit })}
            />
            <p className="text-xs text-[#667085]">达到该上限后会压缩旧会话历史；留空时使用默认值 2400。</p>
            <PrimaryButton
              busy={busy}
              label="创建 Agent"
              onClick={async () => {
                try {
                  await createAgent({
                    name: agentForm.name,
                    description: agentForm.description,
                    modelProvider: agentForm.modelProvider,
                    modelName: agentForm.modelName,
                    systemPrompt: agentForm.systemPrompt,
                    temperature: Number(agentForm.temperature || 0),
                    maxTokens: agentForm.maxTokens ? Number(agentForm.maxTokens) : null,
                    contextTokenLimit: agentForm.contextTokenLimit ? Number(agentForm.contextTokenLimit) : null,
                    defaultWorkflowId: null,
                  });
                  setAgentForm({ name: "", description: "", modelProvider: "", modelName: "", systemPrompt: "", temperature: "0.3", maxTokens: "", contextTokenLimit: "", defaultWorkflowId: "" });
                  showToast("success", "Agent 已创建");
                } catch (error) {
                  showToast("error", error instanceof Error ? error.message : "创建 Agent 失败");
                }
              }}
            />
          </div>
        </Panel>

        <Panel title="Agent 列表" icon={<Network size={17} />}>
          <div className="space-y-2">
            {agents.length === 0 ? <EmptyText text="暂无 Agent" /> : null}
            {agents.map((agent) => (
              <button
                key={agent.agent_id}
                className={`w-full rounded-lg border p-3 text-left text-sm transition ${selectedAgentId === agent.agent_id ? "border-[#2f6feb] bg-[#eef4ff]" : "border-[#dfe4ee] bg-white hover:border-[#93c5fd]"}`}
                onClick={() => setSelectedAgentId(agent.agent_id)}
                type="button"
              >
                <div className="font-medium text-[#172033]">{agent.name}</div>
                <div className="mt-1 text-xs text-[#667085]">{agent.description || agent.agent_id}</div>
              </button>
            ))}
          </div>
        </Panel>
      </div>

      <div className="space-y-6">
        <Panel title="Agent 参数" icon={<Settings size={17} />}>
          {selectedAgent ? (
            <div className="space-y-3">
              <div className="grid gap-3 md:grid-cols-2">
                <TextInput label="名称" value={parameterForm.name} onChange={(name) => setParameterForm({ ...parameterForm, name })} />
                <TextInput label="描述" value={parameterForm.description} onChange={(description) => setParameterForm({ ...parameterForm, description })} />
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <SelectInput
                  label="模型供应商"
                  value={parameterForm.modelProvider}
                  onChange={(modelProvider) =>
                    setParameterForm({
                      ...parameterForm,
                      modelProvider,
                      modelName: modelProviders.find((provider) => provider.provider_key === modelProvider)?.default_model ?? "",
                    })
                  }
                  options={[
                    { label: "暂不绑定默认模型", value: "" },
                    ...modelProviders.map((provider) => ({ label: provider.display_name, value: provider.provider_key })),
                  ]}
                />
                <SelectInput
                  label="默认模型"
                  value={parameterForm.modelName}
                  onChange={(modelName) => setParameterForm({ ...parameterForm, modelName })}
                  options={
                    parameterModelOptions.length > 0
                      ? parameterModelOptions.map((model) => ({ label: model, value: model }))
                      : [{ label: "请先选择模型供应商", value: "" }]
                  }
                />
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <TextInput label="Temperature" type="number" value={parameterForm.temperature} onChange={(temperature) => setParameterForm({ ...parameterForm, temperature })} />
                <TextInput label="Max tokens" type="number" value={parameterForm.maxTokens} onChange={(maxTokens) => setParameterForm({ ...parameterForm, maxTokens })} />
              </div>
              <TextInput
                label="上下文压缩上限（tokens）"
                type="number"
                placeholder="默认 2400，最小 800"
                value={parameterForm.contextTokenLimit}
                onChange={(contextTokenLimit) => setParameterForm({ ...parameterForm, contextTokenLimit })}
              />
              <p className="text-xs text-[#667085]">达到该上限后会压缩旧会话历史；留空时使用默认值 2400。</p>
              <TextArea
                label="系统提示词"
                placeholder="定义 Agent 的角色、边界和输出要求"
                rows={5}
                value={parameterForm.systemPrompt}
                onChange={(systemPrompt) => setParameterForm({ ...parameterForm, systemPrompt })}
              />
              <PrimaryButton
                busy={busy}
                label="保存 Agent 参数"
                onClick={async () => {
                  try {
                    await updateAgent(selectedAgent.agent_id, {
                      name: parameterForm.name,
                      description: parameterForm.description,
                      modelProvider: parameterForm.modelProvider,
                      modelName: parameterForm.modelName,
                      systemPrompt: parameterForm.systemPrompt,
                      temperature: Number(parameterForm.temperature || 0),
                      maxTokens: parameterForm.maxTokens ? Number(parameterForm.maxTokens) : null,
                      contextTokenLimit: parameterForm.contextTokenLimit ? Number(parameterForm.contextTokenLimit) : null,
                      defaultWorkflowId: parameterForm.defaultWorkflowId || null,
                    });
                    showToast("success", "Agent 参数已保存");
                  } catch (error) {
                    showToast("error", error instanceof Error ? error.message : "保存 Agent 参数失败");
                  }
                }}
              />
              <Link
                className="inline-flex text-sm font-medium text-[#2f6feb] hover:underline"
                href={`/insights?agent_id=${encodeURIComponent(selectedAgent.agent_id)}`}
              >
                查看此 Agent 的用量洞察
              </Link>
            </div>
          ) : (
            <EmptyText text="请选择一个 Agent 后修改参数" />
          )}
        </Panel>

        <Panel title="Workflow 策略" icon={<Network size={17} />}>
          {selectedAgent ? (
            <div className="space-y-3">
              <div className="grid gap-2 sm:grid-cols-3">
                <Metric label="Workflows" value={workflows.length} />
                <Metric label="Published" value={workflows.filter((workflow) => workflow.published_version_id).length} />
                <Metric label="Mode" value={parameterForm.defaultWorkflowId ? "流程" : "自主"} />
              </div>
              <SelectInput
                label="默认 Workflow"
                value={parameterForm.defaultWorkflowId}
                onChange={(defaultWorkflowId) => setParameterForm({ ...parameterForm, defaultWorkflowId })}
                options={[
                  { label: "不设置默认流程，使用自主模式", value: "" },
                  ...workflows
                    .filter((workflow) => workflow.published_version_id)
                    .map((workflow) => ({ label: workflow.name, value: workflow.workflow_id })),
                ]}
              />
              <div className="space-y-2">
                {workflows.length === 0 ? <EmptyText text="当前 Agent 暂无 Workflow" /> : null}
                {workflows.slice(0, 5).map((workflow) => (
                  <div key={workflow.workflow_id} className="rounded-lg border border-[#dfe4ee] bg-white px-3 py-2 text-sm">
                    <div className="font-medium text-[#172033]">{workflow.name}</div>
                    <div className="mt-1 text-xs text-[#667085]">
                      {workflow.published_version_id ? "已发布" : "草稿"}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <EmptyText text="请选择 Agent 后配置 Workflow 策略" />
          )}
        </Panel>

        <Panel title="Agent Workspace" icon={<FileText size={17} />}>
          <div className="mb-3 grid gap-2 sm:grid-cols-4">
            <Metric label="Skills" value={skills.length} />
            <Metric label="MCP Tools" value={mcpTools.length} />
            <Metric label="Memories" value={memories.length} />
            <Metric label="Sessions" value={sessions.length} />
          </div>
          <TextArea label="AGENTS.md" placeholder="写入这个 Agent 的运行说明" rows={12} value={workspaceText} onChange={setWorkspaceText} />
          <div className="mt-3 flex items-center justify-between text-xs text-[#667085]">
            <span>{selectedAgent ? `当前 Agent：${selectedAgent.name}` : "请选择 Agent"}</span>
            <button
              className="inline-flex items-center gap-1.5 rounded-lg bg-[#2f6feb] px-3 py-2 text-sm font-medium text-white transition hover:bg-[#255dc7]"
              onClick={async () => {
                if (!selectedAgentId) {
                  showToast("error", "请先选择 Agent");
                  return;
                }
                try {
                  await apiRequest(`/agents/${selectedAgentId}/workspace/file`, {
                    method: "PUT",
                    body: {
                      actor_user_id: workspace.userId,
                      file_kind: "AGENTS.md",
                      content: workspaceText,
                    },
                  });
                  showToast("success", "Agent Workspace 已保存");
                } catch (error) {
                  showToast("error", error instanceof Error ? error.message : "保存 Workspace 失败");
                }
              }}
              type="button"
            >
              <Save size={14} />
              保存 Workspace
            </button>
          </div>
        </Panel>
      </div>
    </div>
  );
}
