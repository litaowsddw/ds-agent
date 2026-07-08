/** Runtime 管理页面。

管理 Model Provider、Skill、MCP Tool、Memory、Session/Context、Gateway。
 */

"use client";

import { useEffect } from "react";
import { Bot, Brain, Database, MessageSquare, Server, ShieldCheck, Sparkles } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useRuntimeStore } from "@/stores/runtime";
import { showToast } from "@/components/layout/AppLayout";
import Panel from "@/components/ui/Panel";
import { TextInput, TextArea } from "@/components/ui/Form";
import { PrimaryButton } from "@/components/ui/Button";
import { Metric, ResourceList } from "@/components/ui/DataDisplay";
import WorkspaceRequired from "@/components/ui/WorkspaceRequired";

export default function RuntimePage() {
  const workspace = useWorkspaceStore((s) => s.workspace);
  const selectedAgentId = useWorkspaceStore((s) => s.selectedAgentId);
  const busy = useWorkspaceStore((s) => s.busy);

  const modelProviders = useRuntimeStore((s) => s.modelProviders);
  const skills = useRuntimeStore((s) => s.skills);
  const skillEvaluations = useRuntimeStore((s) => s.skillEvaluations);
  const mcpServers = useRuntimeStore((s) => s.mcpServers);
  const mcpTools = useRuntimeStore((s) => s.mcpTools);
  const memories = useRuntimeStore((s) => s.memories);
  const sessions = useRuntimeStore((s) => s.sessions);
  const contextBundle = useRuntimeStore((s) => s.contextBundle);
  const gatewayLogs = useRuntimeStore((s) => s.gatewayLogs);

  const providerForm = useRuntimeStore((s) => s.providerForm);
  const skillForm = useRuntimeStore((s) => s.skillForm);
  const mcpForm = useRuntimeStore((s) => s.mcpForm);
  const memoryForm = useRuntimeStore((s) => s.memoryForm);
  const sessionInput = useRuntimeStore((s) => s.sessionInput);

  const setProviderForm = useRuntimeStore((s) => s.setProviderForm);
  const setSkillForm = useRuntimeStore((s) => s.setSkillForm);
  const setMcpForm = useRuntimeStore((s) => s.setMcpForm);
  const setMemoryForm = useRuntimeStore((s) => s.setMemoryForm);
  const setSessionInput = useRuntimeStore((s) => s.setSessionInput);

  const saveModelProvider = useRuntimeStore((s) => s.saveModelProvider);
  const createSkill = useRuntimeStore((s) => s.createSkill);
  const suggestSkillEvaluationPatch = useRuntimeStore((s) => s.suggestSkillEvaluationPatch);
  const createMcpTool = useRuntimeStore((s) => s.createMcpTool);
  const createMemory = useRuntimeStore((s) => s.createMemory);
  const createSessionAndAssembleContext = useRuntimeStore((s) => s.createSessionAndAssembleContext);
  const generateGatewayPreview = useRuntimeStore((s) => s.generateGatewayPreview);
  const refreshRuntimeData = useRuntimeStore((s) => s.refreshRuntimeData);

  useEffect(() => {
    if (workspace) {
      void refreshRuntimeData(workspace.orgId, workspace.userId, selectedAgentId || undefined);
    }
  }, [workspace, selectedAgentId, refreshRuntimeData]);

  if (!workspace) {
    return <WorkspaceRequired />;
  }

  return (
    <div className="grid gap-6 xl:grid-cols-2">
      {/* Model Providers */}
      <Panel title="Model Providers" icon={<Bot size={17} />}>
        <div className="grid gap-2 sm:grid-cols-2">
          <TextInput
            label="Provider Key"
            value={providerForm.providerKey}
            onChange={(providerKey) => setProviderForm({ ...providerForm, providerKey })}
          />
          <TextInput
            label="显示名称"
            value={providerForm.displayName}
            onChange={(displayName) => setProviderForm({ ...providerForm, displayName })}
          />
        </div>
        <TextInput
          label="Base URL"
          value={providerForm.baseUrl}
          onChange={(baseUrl) => setProviderForm({ ...providerForm, baseUrl })}
        />
        <TextInput
          label="API Key"
          value={providerForm.apiKey}
          onChange={(apiKey) => setProviderForm({ ...providerForm, apiKey })}
          type="password"
        />
        <TextInput
          label="模型列表"
          value={providerForm.models}
          onChange={(models) => setProviderForm({ ...providerForm, models })}
        />
        <TextInput
          label="默认模型"
          value={providerForm.defaultModel}
          onChange={(defaultModel) => setProviderForm({ ...providerForm, defaultModel })}
        />
        <PrimaryButton
          busy={busy}
          label="保存模型供应商"
          onClick={async () => {
            try {
              await saveModelProvider(workspace.userId, workspace.orgId);
              showToast("success", "模型供应商已保存。");
            } catch (error) {
              showToast("error", error instanceof Error ? error.message : "保存失败。");
            }
          }}
        />
        <ResourceList
          items={modelProviders.map((p) => `${p.display_name} · ${p.provider_key} · ${p.api_key_masked || "no-key"}`)}
        />
      </Panel>

      {/* Skill Registry */}
      <Panel title="Skill Registry" icon={<Brain size={17} />}>
        <TextInput
          label="Skill 名称"
          value={skillForm.name}
          onChange={(name) => setSkillForm({ ...skillForm, name })}
        />
        <TextInput
          label="说明"
          value={skillForm.description}
          onChange={(description) => setSkillForm({ ...skillForm, description })}
        />
        <PrimaryButton
          busy={busy}
          label="创建并授权 Skill"
          onClick={async () => {
            try {
              await createSkill(workspace.userId, workspace.orgId, selectedAgentId);
              showToast("success", "Skill 已创建并授权。");
            } catch (error) {
              showToast("error", error instanceof Error ? error.message : "创建 Skill 失败。");
            }
          }}
        />
        <ResourceList items={skills.map((s) => `${s.name} · ${s.description}`)} />
      </Panel>

      <Panel title="Skill Evaluation" icon={<Sparkles size={17} />}>
        <div className="mb-3 grid grid-cols-3 gap-2">
          <Metric label="Records" value={skillEvaluations.length} />
          <Metric label="Evaluated" value={skillEvaluations.filter((item) => item.status !== "pending").length} />
          <Metric label="Applied" value={skillEvaluations.filter((item) => item.applied).length} />
        </div>
        <div className="space-y-2">
          {skillEvaluations.length === 0 ? (
            <p className="rounded-lg border border-dashed border-[#dfe4ee] bg-[#f8fafc] px-3 py-3 text-sm text-[#667085]">
              暂无 Skill 调用评价记录。只有真正加载并使用 Skill 后才会记录。
            </p>
          ) : null}
          {skillEvaluations.slice(0, 5).map((evaluation) => (
            <div key={evaluation.evaluation_id} className="rounded-lg border border-[#dfe4ee] bg-white p-3 text-sm">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-medium text-[#172033]">{evaluation.skill_id}</div>
                  <div className="mt-1 truncate text-xs text-[#667085]">{evaluation.user_input}</div>
                </div>
                <span className="shrink-0 rounded-full bg-[#eef4ff] px-2 py-1 text-xs font-medium text-[#2f6feb]">
                  {evaluation.score === null ? evaluation.status : `${Math.round(evaluation.score * 100)}%`}
                </span>
              </div>
              {evaluation.proposed_skill_patch ? (
                <pre className="mt-2 max-h-28 overflow-auto rounded-md bg-[#f8fafc] p-2 text-xs leading-5 text-[#344054]">
                  {evaluation.proposed_skill_patch}
                </pre>
              ) : (
                <button
                  className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-[#cfd7e6] bg-white px-2.5 py-1.5 text-xs font-medium text-[#172033] transition hover:border-[#2f6feb]"
                  onClick={async () => {
                    try {
                      await suggestSkillEvaluationPatch(workspace.userId, evaluation.evaluation_id);
                      showToast("success", "已生成候选改进建议。");
                    } catch (error) {
                      showToast("error", error instanceof Error ? error.message : "生成建议失败。");
                    }
                  }}
                  type="button"
                >
                  <Sparkles size={13} />
                  生成改进建议
                </button>
              )}
            </div>
          ))}
        </div>
      </Panel>

      {/* MCP Tools */}
      <Panel title="MCP Tools" icon={<Server size={17} />}>
        <TextInput
          label="Server 名称"
          value={mcpForm.serverName}
          onChange={(serverName) => setMcpForm({ ...mcpForm, serverName })}
        />
        <TextInput
          label="URL"
          value={mcpForm.url}
          onChange={(url) => setMcpForm({ ...mcpForm, url })}
        />
        <TextInput
          label="Tool 名称"
          value={mcpForm.toolName}
          onChange={(toolName) => setMcpForm({ ...mcpForm, toolName })}
        />
        <PrimaryButton
          busy={busy}
          label="创建 MCP Tool"
          onClick={async () => {
            try {
              await createMcpTool(workspace.userId, workspace.orgId, selectedAgentId);
              showToast("success", "MCP Server 和工具已创建。");
            } catch (error) {
              showToast("error", error instanceof Error ? error.message : "创建 MCP 失败。");
            }
          }}
        />
        <ResourceList
          items={[
            ...mcpServers.map((s) => `Server: ${s.name}`),
            ...mcpTools.map((t) => `Tool: ${t.name}`),
          ]}
        />
      </Panel>

      {/* Memory */}
      <Panel title="Memory" icon={<Database size={17} />}>
        <TextArea label="长期记忆" rows={4} value={memoryForm} onChange={setMemoryForm} />
        <PrimaryButton
          busy={busy}
          label="保存 Memory"
          onClick={async () => {
            try {
              await createMemory(workspace.userId, selectedAgentId);
              showToast("success", "Memory 已保存。");
            } catch (error) {
              showToast("error", error instanceof Error ? error.message : "保存 Memory 失败。");
            }
          }}
        />
        <ResourceList items={memories.map((m) => `${m.memory_type} · ${m.summary}`)} />
      </Panel>

      {/* Session / Context */}
      <Panel title="Session / Context" icon={<MessageSquare size={17} />}>
        <TextArea label="用户消息" rows={4} value={sessionInput} onChange={setSessionInput} />
        <PrimaryButton
          busy={busy}
          label="创建 Session 并组装 Context"
          onClick={async () => {
            try {
              await createSessionAndAssembleContext(workspace.userId, selectedAgentId);
              showToast("success", `Context 已组装：${contextBundle?.sections.length ?? 0} 个片段。`);
            } catch (error) {
              showToast("error", error instanceof Error ? error.message : "组装 Context 失败。");
            }
          }}
        />
        <div className="mt-3 grid grid-cols-2 gap-2">
          <Metric label="Sessions" value={sessions.length} />
          <Metric label="Context Sections" value={contextBundle?.sections.length ?? 0} />
        </div>
      </Panel>

      {/* Gateway */}
      <Panel title="Gateway" icon={<ShieldCheck size={17} />}>
        <p className="mb-3 text-sm leading-6 text-[#667085]">
          通过统一网关调用当前组织已配置的真实模型供应商，并查看 prefix hash 与调用日志。
        </p>
        <PrimaryButton
          busy={busy}
          label="生成预览回复"
          onClick={async () => {
            try {
              await generateGatewayPreview(
                workspace.userId,
                workspace.orgId,
                "请给出一个简短的测试回复。",
                0
              );
              showToast("success", "Gateway 调用完成。");
            } catch (error) {
              showToast("error", error instanceof Error ? error.message : "Gateway 调用失败。");
            }
          }}
        />
        <ResourceList
          items={gatewayLogs
            .slice(0, 5)
            .map((log) => `${log.status} · ${log.provider}/${log.model} · ${log.prefix_hash || "no-prefix"}`)}
        />
      </Panel>
    </div>
  );
}
