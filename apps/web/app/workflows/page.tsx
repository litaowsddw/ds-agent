/** Dify-style workflow workbench backed by real API data. */

"use client";

import {
  CopyPlus,
  Database,
  GitBranch,
  LayoutGrid,
  Play,
  Plus,
  Redo2,
  RotateCcw,
  Save,
  Search,
  Send,
  Sparkles,
  Trash2,
  Undo2,
  Workflow,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { showToast } from "@/components/layout/AppLayout";
import { PrimaryButton } from "@/components/ui/Button";
import { EmptyText, Metric } from "@/components/ui/DataDisplay";
import { SelectInput, TextArea, TextInput } from "@/components/ui/Form";
import AgentRequired from "@/components/ui/AgentRequired";
import WorkspaceRequired from "@/components/ui/WorkspaceRequired";
import WorkflowResponsiveLayout from "@/components/workflows/WorkflowResponsiveLayout";
import WorkflowTemplateLibrary from "@/components/workflows/WorkflowTemplateLibrary";
import WorkflowEditorCanvas from "@/components/workflows/editor/WorkflowEditorCanvas";
import WorkflowVariablePicker, {
  appendWorkflowReference,
  directUpstreamNodes,
} from "@/components/workflows/WorkflowVariablePicker";
import { NODE_PALETTE } from "@/lib/constants";
import { useKnowledgeStore } from "@/stores/knowledge";
import { useRuntimeStore } from "@/stores/runtime";
import { useWorkflowStore } from "@/stores/workflow";
import { useWorkspaceStore } from "@/stores/workspace";
import type { CustomNodeData, NodeRun } from "@/types/workflow";

function stringValue(value: unknown): string {
  if (value === undefined || value === null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value, null, 2);
}

function numberValue(value: unknown, fallback: number): string {
  if (typeof value === "number") return String(value);
  if (typeof value === "string" && value.trim()) return value;
  return String(fallback);
}

const EXECUTABLE_PALETTE = NODE_PALETTE.filter((item) => item.capability === "executable");

export default function WorkflowsPage() {
  const workspace = useWorkspaceStore((state) => state.workspace);
  const agents = useWorkspaceStore((state) => state.agents);
  const selectedAgentId = useWorkspaceStore((state) => state.selectedAgentId);
  const busy = useWorkspaceStore((state) => state.busy);

  const nodes = useWorkflowStore((state) => state.nodes);
  const edges = useWorkflowStore((state) => state.edges);
  const workflows = useWorkflowStore((state) => state.workflows);
  const runs = useWorkflowStore((state) => state.runs);
  const nodeRuns = useWorkflowStore((state) => state.nodeRuns);
  const selectedWorkflowId = useWorkflowStore((state) => state.selectedWorkflowId);
  const selectedNodeId = useWorkflowStore((state) => state.selectedNodeId);
  const workflowForm = useWorkflowStore((state) => state.workflowForm);
  const executionLimits = useWorkflowStore((state) => state.executionLimits);
  const validation = useWorkflowStore((state) => state.validation);
  const canUndo = useWorkflowStore((state) => state.history.past.length > 0);
  const canRedo = useWorkflowStore((state) => state.history.future.length > 0);
  const undo = useWorkflowStore((state) => state.undo);
  const redo = useWorkflowStore((state) => state.redo);
  const applyAutoLayout = useWorkflowStore((state) => state.applyAutoLayout);
  const deleteSelection = useWorkflowStore((state) => state.deleteSelection);
  const addNode = useWorkflowStore((state) => state.addNode);
  const updateSelectedNodeConfig = useWorkflowStore((state) => state.updateSelectedNodeConfig);
  const setWorkflowForm = useWorkflowStore((state) => state.setWorkflowForm);
  const setExecutionLimits = useWorkflowStore((state) => state.setExecutionLimits);
  const applyWorkflowTemplate = useWorkflowStore((state) => state.applyWorkflowTemplate);
  const setSelectedWorkflowId = useWorkflowStore((state) => state.setSelectedWorkflowId);
  const createWorkflow = useWorkflowStore((state) => state.createWorkflow);
  const saveWorkflowDraft = useWorkflowStore((state) => state.saveWorkflowDraft);
  const validateWorkflow = useWorkflowStore((state) => state.validateWorkflow);
  const publishWorkflow = useWorkflowStore((state) => state.publishWorkflow);
  const runWorkflow = useWorkflowStore((state) => state.runWorkflow);
  const refreshWorkflows = useWorkflowStore((state) => state.refreshWorkflows);
  const refreshRuns = useWorkflowStore((state) => state.refreshRuns);
  const resetCanvas = useWorkflowStore((state) => state.resetCanvas);

  const modelProviders = useRuntimeStore((state) => state.modelProviders);
  const mcpTools = useRuntimeStore((state) => state.mcpTools);
  const refreshRuntimeData = useRuntimeStore((state) => state.refreshRuntimeData);

  const knowledgeBases = useKnowledgeStore((state) => state.knowledgeBases);
  const refreshKbs = useKnowledgeStore((state) => state.refreshKbs);

  const selectedNode = nodes.find((node) => node.id === selectedNodeId);
  const selectedWorkflow = workflows.find((workflow) => workflow.workflow_id === selectedWorkflowId);
  const selectedAgent = agents.find((agent) => agent.agent_id === selectedAgentId);
  const [nodeSearch, setNodeSearch] = useState("");
  const [templateOpen, setTemplateOpen] = useState(false);
  const paletteItems = useMemo(() => {
    const query = nodeSearch.trim().toLowerCase();
    if (!query) return EXECUTABLE_PALETTE;
    return EXECUTABLE_PALETTE.filter((item) =>
      `${item.label} ${item.description} ${item.group}`.toLowerCase().includes(query)
    );
  }, [nodeSearch]);
  const latestRun = runs.find((run) => run.workflow_id === selectedWorkflowId);
  const hasWorkflow = Boolean(selectedWorkflowId && selectedWorkflow);
  const isPublished = Boolean(selectedWorkflow?.published_version_id);
  const workflowCanRun = hasWorkflow && isPublished;
  const runDisabledReason = !hasWorkflow
    ? "Create or select a workflow first"
    : !isPublished
      ? "Publish the workflow before running it"
      : "";

  useEffect(() => {
    if (!workspace) return;
    void refreshRuntimeData(workspace.orgId, workspace.userId, selectedAgentId || undefined);
    void refreshKbs(workspace.orgId, workspace.userId);
    void refreshWorkflows(workspace.orgId, workspace.userId, selectedAgentId || undefined);
    void refreshRuns(workspace.orgId, workspace.userId);
  }, [workspace, selectedAgentId, refreshRuntimeData, refreshKbs, refreshWorkflows, refreshRuns]);

  if (!workspace) {
    return <WorkspaceRequired />;
  }

  if (!selectedAgent) {
    return <AgentRequired description="请先选择或创建一个 Agent，再为它设计 Workflow 策略。" />;
  }

  const handleSave = () =>
    void saveWorkflowDraft(workspace.userId)
      .then(() => showToast("success", "Draft saved"))
      .catch((error) => showToast("error", error instanceof Error ? error.message : "Save failed"));

  const handleCheck = () =>
    void validateWorkflow(workspace.userId)
      .then((result) => {
        showToast(result.valid ? "success" : "error", result.valid ? "Preflight passed" : `${result.errors.length} issue(s) need attention`);
      })
      .catch((error) => showToast("error", error instanceof Error ? error.message : "Check failed"));

  const handlePublish = () =>
    void publishWorkflow(workspace.userId)
      .then(() => showToast("success", "Published"))
      .catch((error) => showToast("error", error instanceof Error ? error.message : "Publish failed"));

  const handleRun = () =>
    void runWorkflow(workspace.userId, workflowForm.input)
      .then(() => showToast("success", "Run complete"))
      .catch((error) => showToast("error", error instanceof Error ? error.message : "Run failed"));

  const headerLeft = (
    <div>
      <div className="truncate text-sm font-semibold text-[#172033]">
        {selectedAgent ? selectedAgent.name : "Selected Agent"} · {selectedWorkflow ? selectedWorkflow.name : "Draft"}
        <span className="ml-2 text-xs font-normal text-[#667085]">{nodes.length} nodes · {edges.length} edges</span>
      </div>
      <WorkflowProgress
        hasAgent={Boolean(selectedAgentId)}
        hasWorkflow={hasWorkflow}
        isPublished={isPublished}
        hasRun={Boolean(latestRun)}
      />
    </div>
  );

  const headerRight = (
    <>
      <ToolbarIconButton disabled={!canUndo} icon={<Undo2 size={14} />} onClick={undo} title="撤销 (Ctrl+Z)" />
      <ToolbarIconButton disabled={!canRedo} icon={<Redo2 size={14} />} onClick={redo} title="重做 (Ctrl+Y)" />
      <ToolbarIconButton icon={<LayoutGrid size={14} />} onClick={applyAutoLayout} title="自动布局" />
      <ToolbarIconButton icon={<RotateCcw size={14} />} onClick={resetCanvas} title="重置画布" />
      <ToolbarIconButton icon={<Trash2 size={14} />} danger onClick={deleteSelection} title="删除选中节点或连线 (Delete)" />

      <div className="relative">
        <button
          className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-[#cfd7e6] bg-white px-2.5 text-xs font-medium text-[#172033] transition hover:border-[#2f6feb]"
          onClick={() => setTemplateOpen((open) => !open)}
          type="button"
        >
          <CopyPlus size={14} />
          模板
        </button>
        {templateOpen ? (
          <>
            <button
              aria-label="关闭模板库"
              className="fixed inset-0 z-20 cursor-default"
              onClick={() => setTemplateOpen(false)}
              tabIndex={-1}
              type="button"
            />
            <div className="absolute right-0 top-10 z-30 max-h-[70vh] w-[360px] overflow-y-auto shadow-xl">
              <WorkflowTemplateLibrary
                onSelect={(template) => {
                  applyWorkflowTemplate(template);
                  setTemplateOpen(false);
                  showToast("success", `已载入“${template.name}”新草稿；请完成所需配置后再创建。`);
                }}
              />
            </div>
          </>
        ) : null}
      </div>

      <span className="mx-1 h-5 w-px bg-[#dfe4ee]" />
      <ActionButton icon={<Save size={14} />} label="保存" onClick={handleSave} />
      <ActionButton icon={<Search size={14} />} label="检查" onClick={handleCheck} />
      <ActionButton icon={<Send size={14} />} label="发布" onClick={handlePublish} />
      <ActionButton
        disabled={!workflowCanRun}
        icon={<Play size={14} />}
        label="运行"
        onClick={handleRun}
        title={runDisabledReason || undefined}
      />
    </>
  );

  return (
    <WorkflowResponsiveLayout
      palette={
        <>
          <div className="border-b border-[#dfe4ee] px-4 py-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-[#172033]">
              <Sparkles size={15} />
              Nodes
            </div>
            <div className="mt-1 text-xs text-[#667085]">拖到画布放置，或点击添加到指针位置。</div>
            <label className="mt-3 flex h-9 items-center gap-2 rounded-lg border border-[#dfe4ee] bg-[#f8fafc] px-3 text-sm">
              <Search size={15} className="text-[#667085]" />
              <input
                className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-[#98a2b3]"
                onChange={(event) => setNodeSearch(event.target.value)}
                placeholder="Search nodes"
                value={nodeSearch}
              />
            </label>
          </div>
          <div className="h-[calc(100%-112px)] overflow-y-auto px-3 py-3">
            <div className="space-y-2">
              {paletteItems.map((item) => (
                <button
                  className="w-full cursor-grab rounded-lg border border-[#dfe4ee] bg-white px-3 py-2 text-left transition hover:border-[#2f6feb] hover:bg-[#f8fbff] hover:shadow-sm active:cursor-grabbing"
                  draggable
                  key={item.type}
                  onClick={() => addNode(item)}
                  onDragStart={(event) => {
                    event.dataTransfer.setData("application/agentflow-node", item.type);
                    event.dataTransfer.effectAllowed = "move";
                  }}
                  type="button"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium text-[#172033]">{item.label}</span>
                    <span className="rounded bg-[#ecfdf3] px-1.5 py-0.5 text-[10px] font-semibold text-[#027a48]">live</span>
                  </div>
                  <div className="mt-1 text-xs leading-5 text-[#667085]">{item.description}</div>
                </button>
              ))}
            </div>
            {paletteItems.length === 0 ? <EmptyText text="No matching nodes" /> : null}
          </div>
        </>
      }
      canvas={<WorkflowEditorCanvas headerLeft={headerLeft} headerRight={headerRight} />}
      inspector={
        <>
          <section className="rounded-lg border border-[#dfe4ee] bg-white">
            <div className="border-b border-[#dfe4ee] px-4 py-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-[#172033]">
                <Workflow size={16} />
                Workflow
              </div>
            </div>
            <div className="space-y-3 p-4">
              <div className="grid grid-cols-2 gap-2">
                <Metric label="Workflows" value={workflows.length} />
                <Metric label="Runs" value={runs.length} />
              </div>
              <TextInput label="Name" value={workflowForm.name} onChange={(name) => setWorkflowForm({ ...workflowForm, name })} />
              <TextArea label="Description" rows={2} value={workflowForm.description} onChange={(description) => setWorkflowForm({ ...workflowForm, description })} />
              <TextArea label="Run input" rows={3} value={workflowForm.input} onChange={(input) => setWorkflowForm({ ...workflowForm, input })} />
              <ExecutionLimitsEditor limits={executionLimits} onChange={setExecutionLimits} />
              <PrimaryButton
                busy={busy}
                icon={<Plus size={15} />}
                label="Create"
                onClick={async () => {
                  try {
                    if (!selectedAgentId) throw new Error("Select an agent first");
                    await createWorkflow(workspace.userId, selectedAgentId);
                    showToast("success", "Workflow created");
                  } catch (error) {
                    showToast("error", error instanceof Error ? error.message : "Create failed");
                  }
                }}
              />
              {runDisabledReason ? <ActionHint text={runDisabledReason} /> : null}
              {validation ? <WorkflowPreflight validation={validation} /> : null}
            </div>
          </section>

          <NodeInspector
            edges={edges}
            knowledgeBases={knowledgeBases}
            mcpTools={mcpTools}
            modelProviders={modelProviders}
            node={selectedNode}
            nodes={nodes}
            updateConfig={updateSelectedNodeConfig}
          />

          <section className="rounded-lg border border-[#dfe4ee] bg-white">
            <div className="border-b border-[#dfe4ee] px-4 py-3 text-sm font-semibold text-[#172033]">Saved Workflows</div>
            <div className="space-y-2 p-4">
              {workflows.length === 0 ? <EmptyText text="No saved workflows" /> : null}
              {workflows.slice(0, 6).map((workflow) => (
                <button
                  key={workflow.workflow_id}
                  type="button"
                  onClick={() => setSelectedWorkflowId(workflow.workflow_id)}
                  className={`w-full rounded-lg border p-3 text-left text-sm transition ${selectedWorkflowId === workflow.workflow_id ? "border-[#2f6feb] bg-[#eef4ff]" : "border-[#dfe4ee] bg-white hover:border-[#93c5fd]"}`}
                >
                  <div className="font-medium text-[#172033]">{workflow.name}</div>
                  <div className="mt-1 text-xs text-[#667085]">{workflow.published_version_id ? "published" : "draft"}</div>
                </button>
              ))}
            </div>
          </section>

          <section className="rounded-lg border border-[#dfe4ee] bg-white">
            <div className="border-b border-[#dfe4ee] px-4 py-3 text-sm font-semibold text-[#172033]">Run Trace</div>
            <div className="space-y-2 p-4">
              {nodeRuns.length === 0 ? <EmptyText text="Run a workflow to see node results" /> : null}
              {nodeRuns.map((run) => (
                <NodeRunRow key={run.node_run_id} run={run} />
              ))}
            </div>
          </section>
        </>
      }
    />
  );
}

function ToolbarIconButton({
  danger = false,
  disabled = false,
  icon,
  onClick,
  title,
}: {
  danger?: boolean;
  disabled?: boolean;
  icon: React.ReactNode;
  onClick: () => void;
  title: string;
}) {
  return (
    <button
      className={`inline-flex h-8 w-8 items-center justify-center rounded-lg border border-[#cfd7e6] bg-white text-[#667085] transition disabled:cursor-not-allowed disabled:opacity-40 ${
        danger ? "hover:border-[#b42318] hover:text-[#b42318]" : "hover:border-[#2f6feb] hover:text-[#175cd3]"
      }`}
      disabled={disabled}
      onClick={onClick}
      title={title}
      type="button"
    >
      {icon}
    </button>
  );
}

function WorkflowProgress({
  hasAgent,
  hasWorkflow,
  isPublished,
  hasRun,
}: {
  hasAgent: boolean;
  hasWorkflow: boolean;
  isPublished: boolean;
  hasRun: boolean;
}) {
  const steps = [
    { label: "Agent selected", done: hasAgent },
    { label: "Draft saved", done: hasWorkflow },
    { label: "Published", done: isPublished },
    { label: "Run complete", done: hasRun },
  ];
  return (
    <div className="mt-1.5 flex flex-wrap gap-1.5">
      {steps.map((step) => (
        <span
          key={step.label}
          className={`rounded px-2 py-0.5 text-[11px] font-medium ${
            step.done ? "bg-[#ecfdf3] text-[#027a48]" : "bg-[#f8fafc] text-[#667085]"
          }`}
        >
          {step.label}
        </span>
      ))}
    </div>
  );
}

function WorkflowPreflight({
  validation,
}: {
  validation: { valid: boolean; errors: string[] };
}) {
  if (validation.valid) {
    return (
      <div className="rounded-lg border border-[#abefc6] bg-[#ecfdf3] px-3 py-2 text-xs leading-5 text-[#027a48]">
        运行前检查通过。发布会自动保存当前画布，并使用相同规则再次校验。
      </div>
    );
  }
  return (
    <div className="rounded-lg border border-[#fecdca] bg-[#fef3f2] px-3 py-2 text-xs leading-5 text-[#b42318]">
      <div className="font-semibold">运行前检查发现 {validation.errors.length} 个问题</div>
      <ul className="mt-1 list-disc space-y-1 pl-4">
        {validation.errors.map((error, index) => <li key={`${error}-${index}`}>{error}</li>)}
      </ul>
    </div>
  );
}

function ActionHint({ text }: { text: string }) {
  return <div className="rounded-lg bg-[#f8fafc] px-3 py-2 text-xs text-[#667085]">{text}</div>;
}

function executionLimitError(value: string, minimum: number, maximum: number): string | null {
  const text = value.trim();
  if (!text) return null;
  if (!/^\d+$/.test(text)) return "Enter a whole number or leave this blank.";
  const numeric = Number(text);
  if (numeric < minimum || numeric > maximum) return `Enter a value from ${minimum} to ${maximum}.`;
  return null;
}

function ExecutionLimitsEditor({
  limits,
  onChange,
}: {
  limits: { max_steps: string; max_llm_calls: string };
  onChange: (limits: { max_steps: string; max_llm_calls: string }) => void;
}) {
  const stepError = executionLimitError(limits.max_steps, 1, 500);
  const llmError = executionLimitError(limits.max_llm_calls, 0, 100);
  return (
    <section aria-label="Run protection" className="rounded-lg border border-[#dbeafe] bg-[#f8fbff] p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs font-semibold text-[#175cd3]">Run protection</div>
          <p className="mt-1 text-[11px] leading-4 text-[#475467]">
            Optional hard stops for one workflow run. These limits control execution steps and LLM call count; they are not a money, billing, or token budget.
          </p>
        </div>
        {(limits.max_steps || limits.max_llm_calls) ? (
          <button
            className="shrink-0 text-[11px] font-semibold text-[#175cd3] hover:text-[#1d4ed8]"
            onClick={() => onChange({ max_steps: "", max_llm_calls: "" })}
            type="button"
          >
            Clear
          </button>
        ) : null}
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <div>
          <TextInput
            label="Max steps (optional)"
            onChange={(max_steps) => onChange({ ...limits, max_steps })}
            placeholder="1–500"
            type="number"
            value={limits.max_steps}
          />
          {stepError ? <p role="alert" className="mt-1 text-[11px] text-[#b42318]">{stepError}</p> : null}
        </div>
        <div>
          <TextInput
            label="Max LLM calls (optional)"
            onChange={(max_llm_calls) => onChange({ ...limits, max_llm_calls })}
            placeholder="0–100"
            type="number"
            value={limits.max_llm_calls}
          />
          {llmError ? <p role="alert" className="mt-1 text-[11px] text-[#b42318]">{llmError}</p> : null}
        </div>
      </div>
      <p className="mt-2 text-[11px] leading-4 text-[#667085]">
        Leave either field blank to avoid setting that guard. A value of 0 for LLM calls permits no LLM nodes in the run.
      </p>
    </section>
  );
}

function ActionButton({
  disabled = false,
  icon,
  label,
  onClick,
  title,
}: {
  disabled?: boolean;
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  title?: string;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      title={title}
      className="inline-flex items-center justify-center gap-1 rounded-lg border border-[#cfd7e6] bg-white px-2 py-1.5 text-xs font-medium text-[#172033] transition hover:border-[#2f6feb] disabled:cursor-not-allowed disabled:opacity-50"
    >
      {icon}
      {label}
    </button>
  );
}

function NodeInspector({
  edges,
  knowledgeBases,
  mcpTools,
  modelProviders,
  node,
  nodes,
  updateConfig,
}: {
  edges: Array<{ source: string; target: string; sourceHandle?: string | null }>;
  knowledgeBases: Array<{ kb_id: string; name: string }>;
  mcpTools: Array<{ tool_id: string; name: string; risk_level: string }>;
  modelProviders: Array<{ provider_key: string; display_name: string; models: string[]; default_model: string }>;
  node: { id: string; type?: string; data: CustomNodeData } | undefined;
  nodes: Array<{ id: string; type?: string; data: CustomNodeData }>;
  updateConfig: (patch: Record<string, unknown>) => void;
}) {
  if (!node) {
    return (
      <section className="rounded-lg border border-[#dfe4ee] bg-white p-4">
        <EmptyText text="Select a node to configure it" />
      </section>
    );
  }

  const type = String(node.type ?? "");
  const config = node.data.config ?? {};
  const displayName = stringValue(config.display_name).trim() || node.data.label;
  const displayDescription = stringValue(config.display_description).trim() || node.data.description || "";
  const providerKey = stringValue(config.provider);
  const modelOptions = modelProviders.find((provider) => provider.provider_key === providerKey)?.models ?? [];

  return (
    <section className="rounded-lg border border-[#dfe4ee] bg-white">
      <div className="flex items-center justify-between border-b border-[#dfe4ee] px-4 py-3">
        <div>
          <div className="text-sm font-semibold text-[#172033]">{displayName}</div>
          <div className="mt-1 font-mono text-xs text-[#667085]">{node.id}</div>
        </div>
        <span className={`rounded px-2 py-1 text-[10px] font-semibold uppercase ${node.data.capability === "schema" ? "bg-[#f8fafc] text-[#667085]" : "bg-[#ecfdf3] text-[#027a48]"}`}>
          {node.data.capability === "schema" ? "schema" : "live"}
        </span>
      </div>
      <div className="space-y-3 p-4">
        {type !== "start" && type !== "end" ? (
          <div className="space-y-3 rounded-lg border border-[#dfe4ee] bg-[#f8fafc] p-3">
            <div>
              <div className="text-xs font-semibold text-[#344054]">Node identity</div>
              <div className="mt-1 text-xs leading-5 text-[#667085]">
                Name this step for people reading the canvas. It does not change the node type or execution behavior.
              </div>
            </div>
            <TextInput
              label="Display name"
              onChange={(display_name) => updateConfig({ display_name })}
              placeholder={node.data.label}
              value={displayName}
            />
            <TextArea
              label="Display description"
              onChange={(display_description) => updateConfig({ display_description })}
              placeholder={node.data.description}
              rows={2}
              value={displayDescription}
            />
            <button
              className="text-xs font-medium text-[#2f6feb] hover:text-[#1d4ed8]"
              onClick={() => updateConfig({ display_name: undefined, display_description: undefined })}
              type="button"
            >
              Restore node defaults
            </button>
          </div>
        ) : null}

        {type === "start" || type === "end" ? <EmptyText text="This node has no required configuration" /> : null}

        {type === "llm" ? (
          <>
            <SelectInput
              label="Provider"
              onChange={(provider) => {
                const selected = modelProviders.find((item) => item.provider_key === provider);
                updateConfig({ provider, model: selected?.default_model || selected?.models[0] || "" });
              }}
              options={modelProviders.length ? modelProviders.map((provider) => ({ label: provider.display_name, value: provider.provider_key })) : [{ label: "No providers configured", value: "" }]}
              value={providerKey}
            />
            <SelectInput
              label="Model"
              onChange={(model) => updateConfig({ model })}
              options={modelOptions.length ? modelOptions.map((model) => ({ label: model, value: model })) : [{ label: "No models", value: "" }]}
              value={stringValue(config.model)}
            />
            <TextArea label="System prompt" rows={2} value={stringValue(config.system_prompt)} onChange={(system_prompt) => updateConfig({ system_prompt })} />
            <TextArea label="Prompt" rows={3} value={stringValue(config.prompt)} onChange={(prompt) => updateConfig({ prompt })} />
            <ConfigurationHint>
              The run input and direct predecessor outputs are supplied to the model as separate runtime context. Do not rely on curly-brace text interpolation in an LLM prompt yet.
            </ConfigurationHint>
            <div className="grid grid-cols-2 gap-2">
              <TextInput label="Temperature" value={numberValue(config.temperature, 0)} onChange={(temperature) => updateConfig({ temperature: Number(temperature || 0) })} />
              <TextInput label="Max tokens" value={numberValue(config.max_tokens, 512)} onChange={(max_tokens) => updateConfig({ max_tokens: Number(max_tokens || 0) })} />
            </div>
            <OutputVariableName
              nodeId={node.id}
              onChange={(output_variable) => updateConfig({ output_variable })}
              value={stringValue(config.output_variable)}
            />
          </>
        ) : null}

        {type === "rag" ? (
          <>
            <SelectInput
              label="Knowledge base"
              onChange={(kb_id) => updateConfig({ kb_id })}
              options={knowledgeBases.length ? knowledgeBases.map((kb) => ({ label: kb.name, value: kb.kb_id })) : [{ label: "No knowledge bases", value: "" }]}
              value={stringValue(config.kb_id)}
            />
            <TextInput label="Query template" value={stringValue(config.query_template)} onChange={(query_template) => updateConfig({ query_template })} />
            <WorkflowVariablePicker
              edges={edges}
              nodeId={node.id}
              nodes={nodes}
              onInsert={(reference) => updateConfig({
                query_template: appendWorkflowReference(stringValue(config.query_template), reference),
              })}
            />
            <TextInput label="Limit" value={numberValue(config.limit, 5)} onChange={(limit) => updateConfig({ limit: Number(limit || 5) })} />
            <OutputVariableName
              nodeId={node.id}
              onChange={(output_variable) => updateConfig({ output_variable })}
              value={stringValue(config.output_variable)}
            />
          </>
        ) : null}

        {type === "tool" ? (
          <>
            <SelectInput
              label="Authorized tool"
              onChange={(tool_id) => {
                const tool = mcpTools.find((item) => item.tool_id === tool_id);
                updateConfig({ tool_id, tool_name: tool?.name, risk_level: tool?.risk_level ?? "low" });
              }}
              options={mcpTools.length ? mcpTools.map((tool) => ({ label: tool.name, value: tool.tool_id })) : [{ label: "No tools authorized", value: "" }]}
              value={stringValue(config.tool_id)}
            />
            <SelectInput
              label="Risk"
              onChange={(risk_level) => updateConfig({ risk_level })}
              options={["low", "medium", "high", "critical"].map((item) => ({ label: item, value: item }))}
              value={stringValue(config.risk_level) || "low"}
            />
            <ToolArgumentsInput
              onChange={(argumentsValue) => updateConfig({ arguments: argumentsValue })}
              value={stringValue(config.arguments)}
            />
            <OutputVariableName
              nodeId={node.id}
              onChange={(output_variable) => updateConfig({ output_variable })}
              value={stringValue(config.output_variable)}
            />
          </>
        ) : null}

        {type === "condition" ? (
          <>
            <ConditionReferencePicker
              edges={edges}
              node={node}
              nodes={nodes}
              onChange={(left) => updateConfig({ left })}
              value={stringValue(config.left)}
            />
            <SelectInput
              label="Check"
              onChange={(operator) => updateConfig({
                operator,
                value: operator === "equals" ? config.value ?? "" : undefined,
              })}
              options={[
                { label: "Exists", value: "exists" },
                { label: "Equals", value: "equals" },
              ]}
              value={stringValue(config.operator) || "equals"}
            />
            {stringValue(config.operator) !== "exists" ? (
              <ConditionScalarValue
                onChange={(patch) => updateConfig(patch)}
                value={config.value}
                valueType={stringValue(config.value_type) || conditionValueType(config.value)}
              />
            ) : (
              <ConfigurationHint>
                Exists is true for non-empty strings, lists, objects, numbers, and booleans. It is false for null or an empty value.
              </ConfigurationHint>
            )}
            <ConfigurationHint>
              Condition only evaluates this selected data value. It never runs code or an arbitrary expression. Connect exactly one <strong>true</strong> and one <strong>false</strong> output branch.
            </ConfigurationHint>
          </>
        ) : null}
      </div>
    </section>
  );
}

function ConfigurationHint({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-[#dbeafe] bg-[#f8fbff] px-3 py-2 text-xs leading-5 text-[#475467]">
      {children}
    </div>
  );
}

function conditionValueType(value: unknown): "string" | "number" | "boolean" | "null" {
  if (value === null) return "null";
  if (typeof value === "number") return "number";
  if (typeof value === "boolean") return "boolean";
  return "string";
}

function ConditionReferencePicker({
  edges,
  node,
  nodes,
  onChange,
  value,
}: {
  edges: Array<{ source: string; target: string; sourceHandle?: string | null }>;
  node: { id: string; type?: string; data: CustomNodeData };
  nodes: Array<{ id: string; type?: string; data: CustomNodeData }>;
  onChange: (value: string) => void;
  value: string;
}) {
  const upstream = directUpstreamNodes(nodes, edges, node.id);
  const options = [
    { label: "Run input: text", value: "{{input.text}}" },
    { label: "Run input: status", value: "{{input.status}}" },
    { label: "Run input: approved", value: "{{input.approved}}" },
    ...upstream.flatMap((upstreamNode) => conditionUpstreamReferences(upstreamNode)),
  ];
  if (value && !options.some((option) => option.value === value)) {
    options.unshift({ label: `Custom reference: ${value}`, value });
  }

  return (
    <div className="space-y-2">
      <SelectInput
        label="Data reference"
        onChange={onChange}
        options={options}
        value={value || "{{input.text}}"}
      />
      <TextInput
        label="Custom input or upstream field"
        onChange={onChange}
        placeholder="{{input.customer_tier}} or {{upstream.classify.label}}"
        value={value}
      />
      <p className="text-[11px] leading-4 text-[#667085]">
        Choose a known run-input field or direct upstream output above. A custom reference must use the same <code>{"{{input.field}}"}</code> or <code>{"{{upstream.node.field}}"}</code> format.
      </p>
    </div>
  );
}

function conditionUpstreamReferences(node: { id: string; type?: string; data: CustomNodeData }) {
  const label = canvasNodeLabel(node);
  const outputFields: Record<string, Array<{ field: string; label: string }>> = {
    start: [{ field: "input", label: "input" }],
    llm: [{ field: "text", label: "text" }],
    rag: [{ field: "chunks", label: "chunks" }],
    tool: [{ field: "status", label: "status" }],
    condition: [{ field: "result", label: "result" }],
  };
  const fields = outputFields[String(node.type ?? "")] ?? [{ field: "result", label: "result" }];
  return fields.map(({ field, label: fieldLabel }) => ({
    label: `${label}: ${fieldLabel}`,
    value: `{{upstream.${node.id}.${field}}}`,
  }));
}

function ConditionScalarValue({
  onChange,
  value,
  valueType,
}: {
  onChange: (patch: Record<string, unknown>) => void;
  value: unknown;
  valueType: "string" | "number" | "boolean" | "null" | string;
}) {
  const normalizedType = ["string", "number", "boolean", "null"].includes(valueType)
    ? valueType as "string" | "number" | "boolean" | "null"
    : conditionValueType(value);
  const setType = (nextType: string) => {
    const defaults: Record<string, string | number | boolean | null> = {
      string: "",
      number: 0,
      boolean: false,
      null: null,
    };
    onChange({ value_type: nextType, value: defaults[nextType] });
  };

  return (
    <div className="space-y-2 rounded-lg border border-[#dfe4ee] bg-[#f8fafc] p-3">
      <SelectInput
        label="Expected value type"
        onChange={setType}
        options={[
          { label: "Text", value: "string" },
          { label: "Number", value: "number" },
          { label: "Boolean", value: "boolean" },
          { label: "Null", value: "null" },
        ]}
        value={normalizedType}
      />
      {normalizedType === "string" ? (
        <TextInput label="Expected text" onChange={(nextValue) => onChange({ value: nextValue })} value={stringValue(value)} />
      ) : null}
      {normalizedType === "number" ? (
        <TextInput
          label="Expected number"
          onChange={(nextValue) => onChange({ value: Number(nextValue || 0) })}
          type="number"
          value={stringValue(value)}
        />
      ) : null}
      {normalizedType === "boolean" ? (
        <SelectInput
          label="Expected boolean"
          onChange={(nextValue) => onChange({ value: nextValue === "true" })}
          options={[{ label: "true", value: "true" }, { label: "false", value: "false" }]}
          value={value === true ? "true" : "false"}
        />
      ) : null}
      {normalizedType === "null" ? <p className="text-xs text-[#667085]">This branch matches only when the selected value is null.</p> : null}
    </div>
  );
}

function OutputVariableName({
  nodeId,
  onChange,
  value,
}: {
  nodeId: string;
  onChange: (value: string) => void;
  value: string;
}) {
  const isValid = !value.trim() || /^[A-Za-z_][A-Za-z0-9_]*$/.test(value.trim());
  return (
    <div className="space-y-1.5 rounded-lg border border-[#dfe4ee] bg-[#f8fafc] p-3">
      <TextInput
        label="Output variable name"
        onChange={onChange}
        placeholder="e.g. customer_summary"
        value={value}
      />
      {!isValid ? (
        <p role="alert" className="text-xs text-[#b42318]">
          Use letters, numbers, and underscores; start with a letter or underscore.
        </p>
      ) : null}
      <p className="text-[11px] leading-4 text-[#667085]">
        This alias is saved with the workflow to document the intended output. The current executor keeps the actual output under immutable node key <code className="rounded bg-white px-1">upstream.{nodeId}</code>; it does not remap runtime fields yet.
      </p>
    </div>
  );
}

function ToolArgumentsInput({
  onChange,
  value,
}: {
  onChange: (value: string) => void;
  value: string;
}) {
  const error = jsonObjectError(value);
  return (
    <div className="space-y-1.5">
      <TextArea label="Arguments (JSON object)" rows={5} value={value} onChange={onChange} />
      {error ? <p role="alert" className="text-xs text-[#b42318]">{error}</p> : null}
      <p className="text-[11px] leading-4 text-[#667085]">
        Parameters are saved as a JSON object and validated again before publishing. Use {"{{input.field}}"} or {"{{node_id.field}}"} to pass runtime values; a reference on its own preserves JSON types.
      </p>
    </div>
  );
}

function jsonObjectError(value: string): string | null {
  if (!value.trim()) return null;
  try {
    const parsed: unknown = JSON.parse(value);
    if (parsed === null || Array.isArray(parsed) || typeof parsed !== "object") {
      return "Tool arguments must be a JSON object, for example {\"query\": \"refund policy\"}.";
    }
    return null;
  } catch {
    return "Enter valid JSON before publishing this tool step.";
  }
}

function canvasNodeLabel(node: { id: string; data: CustomNodeData } | undefined): string {
  if (!node) return "Unknown step";
  const config = node.data.config ?? {};
  return stringValue(config.display_name).trim() || node.data.label || node.id;
}

function NodeRunRow({ run }: { run: NodeRun }) {
  const ok = run.status === "succeeded";
  return (
    <div className="rounded-lg border border-[#dfe4ee] bg-white px-3 py-2 text-sm">
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium text-[#172033]">{run.node_id}</span>
        <span className={`rounded px-2 py-0.5 text-[10px] font-semibold ${ok ? "bg-[#ecfdf3] text-[#027a48]" : "bg-[#fef2f2] text-[#b42318]"}`}>
          {run.status}
        </span>
      </div>
      <div className="mt-1 flex items-center gap-2 text-xs text-[#667085]">
        <Database size={12} />
        {run.node_type}
        <GitBranch size={12} />
        {run.elapsed_ms}ms
      </div>
      {run.error_message ? (
        <div className="mt-2 rounded bg-[#fef2f2] px-2 py-1 text-xs text-[#b42318]">{run.error_message}</div>
      ) : null}
    </div>
  );
}
