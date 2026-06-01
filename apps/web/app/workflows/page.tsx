/** Workflow 编辑页面。

Dify 风格的工作流编辑器：左侧画布 + 右侧配置面板。
使用自定义 React Flow 节点。
 */

"use client";

import "@xyflow/react/dist/style.css";

import { useEffect } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
} from "@xyflow/react";
import {
  Bot,
  Database,
  FileText,
  GitBranch,
  Play,
  Save,
  Send,
  Workflow,
} from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useWorkflowStore } from "@/stores/workflow";
import { useRuntimeStore } from "@/stores/runtime";
import { useKnowledgeStore } from "@/stores/knowledge";
import { showToast } from "@/components/layout/AppLayout";
import { nodeTypes } from "@/components/nodes";
import Panel from "@/components/ui/Panel";
import { TextInput, TextArea, SelectInput } from "@/components/ui/Form";
import { PrimaryButton, SecondaryButton } from "@/components/ui/Button";
import { Metric, EmptyText } from "@/components/ui/DataDisplay";
import { NODE_PALETTE } from "@/lib/constants";

export default function WorkflowsPage() {
  const workspace = useWorkspaceStore((s) => s.workspace);
  const agents = useWorkspaceStore((s) => s.agents);
  const selectedAgentId = useWorkspaceStore((s) => s.selectedAgentId);
  const busy = useWorkspaceStore((s) => s.busy);

  const nodes = useWorkflowStore((s) => s.nodes);
  const edges = useWorkflowStore((s) => s.edges);
  const workflows = useWorkflowStore((s) => s.workflows);
  const selectedWorkflowId = useWorkflowStore((s) => s.selectedWorkflowId);
  const workflowForm = useWorkflowStore((s) => s.workflowForm);
  const llmNodeForm = useWorkflowStore((s) => s.llmNodeForm);
  const ragNodeForm = useWorkflowStore((s) => s.ragNodeForm);
  const toolNodeForm = useWorkflowStore((s) => s.toolNodeForm);

  const onNodesChange = useWorkflowStore((s) => s.onNodesChange);
  const onEdgesChange = useWorkflowStore((s) => s.onEdgesChange);
  const onConnect = useWorkflowStore((s) => s.onConnect);
  const addNode = useWorkflowStore((s) => s.addNode);
  const setLLMNodeForm = useWorkflowStore((s) => s.setLLMNodeForm);
  const setRAGNodeForm = useWorkflowStore((s) => s.setRAGNodeForm);
  const setToolNodeForm = useWorkflowStore((s) => s.setToolNodeForm);
  const setWorkflowForm = useWorkflowStore((s) => s.setWorkflowForm);
  const setSelectedWorkflowId = useWorkflowStore((s) => s.setSelectedWorkflowId);
  const createWorkflow = useWorkflowStore((s) => s.createWorkflow);
  const saveWorkflowDraft = useWorkflowStore((s) => s.saveWorkflowDraft);
  const publishWorkflow = useWorkflowStore((s) => s.publishWorkflow);
  const runWorkflow = useWorkflowStore((s) => s.runWorkflow);
  const getWorkflowDraft = useWorkflowStore((s) => s.getWorkflowDraft);

  const modelProviders = useRuntimeStore((s) => s.modelProviders);
  const selectedProviderKey = useRuntimeStore((s) => s.selectedProviderKey);
  const selectedModel = useRuntimeStore((s) => s.selectedModel);
  const setSelectedProviderKey = useRuntimeStore((s) => s.setSelectedProviderKey);
  const setSelectedModel = useRuntimeStore((s) => s.setSelectedModel);
  const mcpTools = useRuntimeStore((s) => s.mcpTools);

  const knowledgeBases = useKnowledgeStore((s) => s.knowledgeBases);
  const selectedKbId = useKnowledgeStore((s) => s.selectedKbId);
  const setSelectedKbId = useKnowledgeStore((s) => s.setSelectedKbId);

  const modelOptions =
    selectedProviderKey === "mock"
      ? ["mock-model"]
      : modelProviders.find((p) => p.provider_key === selectedProviderKey)?.models ?? ["mock-model"];

  // 初始化刷新数据
  useEffect(() => {
    if (workspace) {
      const runtimeRefresh = useRuntimeStore.getState().refreshRuntimeData;
      void runtimeRefresh(workspace.orgId, workspace.userId, selectedAgentId || undefined);
      void useKnowledgeStore.getState().refreshKbs(workspace.orgId, workspace.userId);
      void useWorkflowStore.getState().refreshWorkflows(workspace.orgId, workspace.userId);
      void useWorkflowStore.getState().refreshRuns(workspace.orgId, workspace.userId);
    }
  }, [workspace, selectedAgentId]);

  if (!workspace) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-[#667085]">
        请先在首页创建工作空间
      </div>
    );
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
      {/* 画布 */}
      <div className="space-y-4">
        <div className="h-[calc(100vh-12rem)] overflow-hidden rounded-xl border border-[#dfe4ee] bg-white shadow-sm">
          <div className="border-b border-[#dfe4ee] px-4 py-3">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold text-[#172033]">Workflow 画布</h3>
                <p className="mt-0.5 text-xs text-[#667085]">
                  拖拽节点、连线，然后保存草稿、发布并运行
                </p>
              </div>
              <div className="flex gap-2">
                {NODE_PALETTE.map((item) => (
                  <button
                    key={item.label}
                    className="rounded-lg border border-[#dfe4ee] bg-white px-3 py-1.5 text-xs font-medium text-[#344054] transition hover:border-[#2f6feb] hover:text-[#2f6feb]"
                    onClick={() => addNode(item.label, item.type)}
                    type="button"
                  >
                    + {item.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            nodeTypes={nodeTypes}
            fitView
          >
            <Background color="#d9e0ec" gap={18} />
            <Controls />
            <MiniMap
              pannable
              zoomable
              nodeStrokeWidth={3}
              className="!rounded-lg !border !border-[#dfe4ee] !shadow-sm"
            />
          </ReactFlow>
        </div>
      </div>

      {/* 配置面板 */}
      <div className="space-y-4">
        <Panel title="Workflow 配置" icon={<Workflow size={17} />}>
          <div className="space-y-3">
            <TextInput
              label="名称"
              value={workflowForm.name}
              onChange={(name) => setWorkflowForm({ ...workflowForm, name })}
            />
            <TextArea
              label="描述"
              rows={2}
              value={workflowForm.description}
              onChange={(description) => setWorkflowForm({ ...workflowForm, description })}
            />
            <TextArea
              label="运行输入"
              rows={3}
              value={workflowForm.input}
              onChange={(input) => setWorkflowForm({ ...workflowForm, input })}
            />

            {/* LLM 节点配置 */}
            <div className="rounded-lg border border-[#93c5fd] bg-[#eef4ff] p-3">
              <div className="mb-3 text-xs font-semibold text-[#1e40af]">LLM 节点模型</div>
              <div className="grid gap-2 sm:grid-cols-2">
                <SelectInput
                  label="供应商"
                  value={selectedProviderKey}
                  options={[
                    { label: "Mock / 本地测试", value: "mock" },
                    ...modelProviders.map((p) => ({
                      label: p.display_name,
                      value: p.provider_key,
                    })),
                  ]}
                  onChange={setSelectedProviderKey}
                />
                <SelectInput
                  label="模型"
                  value={selectedModel}
                  options={modelOptions.map((m) => ({ label: m, value: m }))}
                  onChange={setSelectedModel}
                />
              </div>
              <TextArea
                label="系统提示词"
                rows={2}
                value={llmNodeForm.systemPrompt}
                onChange={(systemPrompt) => setLLMNodeForm({ ...llmNodeForm, systemPrompt })}
              />
              <TextArea
                label="节点提示词"
                rows={2}
                value={llmNodeForm.prompt}
                onChange={(prompt) => setLLMNodeForm({ ...llmNodeForm, prompt })}
              />
              <TextInput
                label="Temperature"
                value={llmNodeForm.temperature}
                onChange={(temperature) => setLLMNodeForm({ ...llmNodeForm, temperature })}
              />
            </div>

            {/* RAG 节点配置 */}
            <div className="rounded-lg border border-[#fde047] bg-[#fefce8] p-3">
              <div className="mb-3 text-xs font-semibold text-[#854d0e]">RAG 节点检索</div>
              <SelectInput
                label="知识库"
                value={selectedKbId}
                options={
                  knowledgeBases.length > 0
                    ? knowledgeBases.map((kb) => ({ label: kb.name, value: kb.kb_id }))
                    : [{ label: "请先在 Knowledge 创建知识库", value: "" }]
                }
                onChange={setSelectedKbId}
              />
              <TextInput
                label="Limit"
                value={ragNodeForm.limit}
                onChange={(limit) => setRAGNodeForm({ ...ragNodeForm, limit })}
              />
            </div>

            {/* 操作按钮 */}
            <PrimaryButton
              busy={busy}
              label="创建 Workflow"
              onClick={async () => {
                try {
                  await createWorkflow(workspace.userId, selectedAgentId);
                  showToast("success", "Workflow 已创建。");
                } catch (error) {
                  showToast("error", error instanceof Error ? error.message : "创建失败。");
                }
              }}
            />
            <div className="grid grid-cols-3 gap-2">
              <SecondaryButton
                label="保存"
                onClick={async () => {
                  try {
                    await saveWorkflowDraft(workspace.userId);
                    showToast("success", "草稿已保存。");
                  } catch (error) {
                    showToast("error", error instanceof Error ? error.message : "保存失败。");
                  }
                }}
              />
              <SecondaryButton
                label="发布"
                onClick={async () => {
                  try {
                    await publishWorkflow(workspace.userId);
                    showToast("success", "Workflow 已发布。");
                  } catch (error) {
                    showToast("error", error instanceof Error ? error.message : "发布失败。");
                  }
                }}
              />
              <SecondaryButton
                label="运行"
                onClick={async () => {
                  try {
                    await runWorkflow(workspace.userId, workflowForm.input);
                    showToast("success", "Workflow 已运行。");
                  } catch (error) {
                    showToast("error", error instanceof Error ? error.message : "运行失败。");
                  }
                }}
              />
            </div>
          </div>
        </Panel>

        {/* Workflow 列表 */}
        <Panel title="Workflow 列表" icon={<GitBranch size={17} />}>
          <div className="space-y-2">
            {workflows.length === 0 ? <EmptyText text="暂无 Workflow。" /> : null}
            {workflows.map((wf) => (
              <button
                key={wf.workflow_id}
                className={`w-full rounded-lg border p-3 text-left text-sm transition ${
                  selectedWorkflowId === wf.workflow_id
                    ? "border-[#2f6feb] bg-[#eef4ff]"
                    : "border-[#dfe4ee] bg-white hover:border-[#93c5fd]"
                }`}
                onClick={() => setSelectedWorkflowId(wf.workflow_id)}
                type="button"
              >
                <div className="font-medium text-[#172033]">{wf.name}</div>
                <div className="mt-1 text-xs text-[#667085]">
                  {wf.published_version_id ? "已发布" : "草稿"}
                </div>
              </button>
            ))}
          </div>
        </Panel>

        {/* DSL 预览 */}
        <Panel title="DSL 预览" icon={<FileText size={17} />}>
          <pre className="max-h-[220px] overflow-auto rounded-lg bg-[#0f172a] p-3 text-xs leading-5 text-[#dbeafe]">
            {JSON.stringify(getWorkflowDraft(), null, 2)}
          </pre>
        </Panel>
      </div>
    </div>
  );
}
