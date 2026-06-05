/** Dify-style workflow workbench backed by real API data. */

"use client";

import "@xyflow/react/dist/style.css";

import { Background, Controls, MiniMap, ReactFlow, type NodeMouseHandler } from "@xyflow/react";
import {
  Database,
  GitBranch,
  MousePointer2,
  Play,
  Plus,
  RotateCcw,
  Save,
  Search,
  Send,
  Sparkles,
  Trash2,
  Workflow,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { showToast } from "@/components/layout/AppLayout";
import { nodeTypes } from "@/components/nodes";
import { PrimaryButton } from "@/components/ui/Button";
import { EmptyText, Metric } from "@/components/ui/DataDisplay";
import { SelectInput, TextArea, TextInput } from "@/components/ui/Form";
import { NODE_PALETTE, type WorkflowPaletteItem } from "@/lib/constants";
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

function groupedPalette(items: WorkflowPaletteItem[]) {
  return items.reduce<Record<string, WorkflowPaletteItem[]>>((groups, item) => {
    groups[item.group] = [...(groups[item.group] ?? []), item];
    return groups;
  }, {});
}

export default function WorkflowsPage() {
  const workspace = useWorkspaceStore((state) => state.workspace);
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
  const onNodesChange = useWorkflowStore((state) => state.onNodesChange);
  const onEdgesChange = useWorkflowStore((state) => state.onEdgesChange);
  const onConnect = useWorkflowStore((state) => state.onConnect);
  const addNode = useWorkflowStore((state) => state.addNode);
  const removeSelectedNode = useWorkflowStore((state) => state.removeSelectedNode);
  const setSelectedNodeId = useWorkflowStore((state) => state.setSelectedNodeId);
  const updateSelectedNodeConfig = useWorkflowStore((state) => state.updateSelectedNodeConfig);
  const setWorkflowForm = useWorkflowStore((state) => state.setWorkflowForm);
  const setSelectedWorkflowId = useWorkflowStore((state) => state.setSelectedWorkflowId);
  const createWorkflow = useWorkflowStore((state) => state.createWorkflow);
  const saveWorkflowDraft = useWorkflowStore((state) => state.saveWorkflowDraft);
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
  const [nodeSearch, setNodeSearch] = useState("");
  const paletteGroups = useMemo(() => {
    const query = nodeSearch.trim().toLowerCase();
    const items = query
      ? NODE_PALETTE.filter((item) =>
          `${item.label} ${item.description} ${item.group}`.toLowerCase().includes(query)
        )
      : NODE_PALETTE;
    return groupedPalette(items);
  }, [nodeSearch]);

  useEffect(() => {
    if (!workspace) return;
    void refreshRuntimeData(workspace.orgId, workspace.userId, selectedAgentId || undefined);
    void refreshKbs(workspace.orgId, workspace.userId);
    void refreshWorkflows(workspace.orgId, workspace.userId);
    void refreshRuns(workspace.orgId, workspace.userId);
  }, [workspace, selectedAgentId, refreshRuntimeData, refreshKbs, refreshWorkflows, refreshRuns]);

  const handleNodeClick: NodeMouseHandler = (_, node) => {
    setSelectedNodeId(node.id);
  };

  if (!workspace) {
    return <div className="flex h-64 items-center justify-center text-sm text-[#667085]">Create a workspace first</div>;
  }

  return (
    <div className="grid h-[calc(100vh-7rem)] min-h-[720px] gap-4 xl:grid-cols-[280px_minmax(0,1fr)_400px]">
      <aside className="min-h-0 overflow-hidden rounded-lg border border-[#dfe4ee] bg-white">
        <div className="border-b border-[#dfe4ee] px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-[#172033]">
            <Sparkles size={15} />
            Nodes
          </div>
          <div className="mt-1 text-xs text-[#667085]">Click a node to insert it after the selected step.</div>
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
          {Object.entries(paletteGroups).map(([group, items]) => (
            <div key={group} className="mb-4">
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-normal text-[#667085]">{group}</div>
              <div className="space-y-2">
                {items.map((item) => (
                  <button
                    key={item.type}
                    type="button"
                    onClick={() => addNode(item)}
                    className="w-full rounded-lg border border-[#dfe4ee] bg-white px-3 py-2 text-left transition hover:border-[#2f6feb] hover:bg-[#f8fbff] hover:shadow-sm"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium text-[#172033]">{item.label}</span>
                      <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${item.capability === "executable" ? "bg-[#ecfdf3] text-[#027a48]" : "bg-[#f8fafc] text-[#667085]"}`}>
                        {item.capability === "executable" ? "live" : "schema"}
                      </span>
                    </div>
                    <div className="mt-1 text-xs leading-5 text-[#667085]">{item.description}</div>
                  </button>
                ))}
              </div>
            </div>
          ))}
          {Object.keys(paletteGroups).length === 0 ? <EmptyText text="No matching nodes" /> : null}
        </div>
      </aside>

      <main className="min-h-0 overflow-hidden rounded-lg border border-[#dfe4ee] bg-white">
        <div className="flex items-center justify-between border-b border-[#dfe4ee] px-4 py-3">
          <div>
            <div className="text-sm font-semibold text-[#172033]">Workflow Canvas</div>
            <div className="mt-1 text-xs text-[#667085]">
              {selectedWorkflow ? selectedWorkflow.name : "Draft"} · {nodes.length} nodes · {edges.length} edges
            </div>
          </div>
          <div className="flex items-center gap-2">
            <ActionButton icon={<RotateCcw size={14} />} label="Reset" onClick={resetCanvas} />
            <button
              type="button"
              onClick={removeSelectedNode}
              className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-[#cfd7e6] bg-white text-[#667085] transition hover:border-[#b42318] hover:text-[#b42318]"
              title="Delete selected node"
            >
              <Trash2 size={16} />
            </button>
          </div>
        </div>

        <div className="relative h-[calc(100%-58px)] bg-[#f7f8fa]">
          <ReactFlow
            connectionLineStyle={{ stroke: "#2f6feb", strokeWidth: 2 }}
            defaultEdgeOptions={{
              animated: true,
              style: { stroke: "#94a3b8", strokeWidth: 2 },
              type: "smoothstep",
            }}
            edges={edges}
            fitView
            fitViewOptions={{ padding: 0.22 }}
            nodeTypes={nodeTypes}
            nodes={nodes}
            onConnect={onConnect}
            onEdgesChange={onEdgesChange}
            onNodeClick={handleNodeClick}
            onNodesChange={onNodesChange}
            panOnScroll
            selectionOnDrag
            snapGrid={[20, 20]}
            snapToGrid
          >
            <Background color="#d9e0ec" gap={18} />
            <Controls />
            <MiniMap pannable zoomable className="!rounded-lg !border !border-[#dfe4ee] !shadow-sm" nodeStrokeWidth={3} />
          </ReactFlow>
          <div className="pointer-events-none absolute left-4 top-4 flex items-center gap-2 rounded-lg border border-[#dfe4ee] bg-white/90 px-3 py-2 text-xs text-[#667085] shadow-sm">
            <MousePointer2 size={14} />
            Select a node, then add from the left to insert into the chain.
          </div>
        </div>
      </main>

      <aside className="min-h-0 overflow-y-auto space-y-4">
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
            <div className="grid grid-cols-3 gap-2">
              <ActionButton icon={<Save size={14} />} label="Save" onClick={() => void saveWorkflowDraft(workspace.userId).then(() => showToast("success", "Draft saved")).catch((error) => showToast("error", error instanceof Error ? error.message : "Save failed"))} />
              <ActionButton icon={<Send size={14} />} label="Publish" onClick={() => void publishWorkflow(workspace.userId).then(() => showToast("success", "Published")).catch((error) => showToast("error", error instanceof Error ? error.message : "Publish failed"))} />
              <ActionButton icon={<Play size={14} />} label="Run" onClick={() => void runWorkflow(workspace.userId, workflowForm.input).then(() => showToast("success", "Run complete")).catch((error) => showToast("error", error instanceof Error ? error.message : "Run failed"))} />
            </div>
          </div>
        </section>

        <NodeInspector
          knowledgeBases={knowledgeBases}
          mcpTools={mcpTools}
          modelProviders={modelProviders}
          node={selectedNode}
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
      </aside>
    </div>
  );
}

function ActionButton({ icon, label, onClick }: { icon: React.ReactNode; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center justify-center gap-1 rounded-lg border border-[#cfd7e6] bg-white px-2 py-2 text-xs font-medium text-[#172033] transition hover:border-[#2f6feb]"
    >
      {icon}
      {label}
    </button>
  );
}

function NodeInspector({
  knowledgeBases,
  mcpTools,
  modelProviders,
  node,
  updateConfig,
}: {
  knowledgeBases: Array<{ kb_id: string; name: string }>;
  mcpTools: Array<{ tool_id: string; name: string; risk_level: string }>;
  modelProviders: Array<{ provider_key: string; display_name: string; models: string[]; default_model: string }>;
  node: { id: string; type?: string; data: CustomNodeData } | undefined;
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
  const providerKey = stringValue(config.provider);
  const modelOptions = modelProviders.find((provider) => provider.provider_key === providerKey)?.models ?? [];

  return (
    <section className="rounded-lg border border-[#dfe4ee] bg-white">
      <div className="flex items-center justify-between border-b border-[#dfe4ee] px-4 py-3">
        <div>
          <div className="text-sm font-semibold text-[#172033]">{node.data.label}</div>
          <div className="mt-1 font-mono text-xs text-[#667085]">{node.id}</div>
        </div>
        <span className={`rounded px-2 py-1 text-[10px] font-semibold uppercase ${node.data.capability === "schema" ? "bg-[#f8fafc] text-[#667085]" : "bg-[#ecfdf3] text-[#027a48]"}`}>
          {node.data.capability === "schema" ? "schema" : "live"}
        </span>
      </div>
      <div className="space-y-3 p-4">
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
            <div className="grid grid-cols-2 gap-2">
              <TextInput label="Temperature" value={numberValue(config.temperature, 0)} onChange={(temperature) => updateConfig({ temperature: Number(temperature || 0) })} />
              <TextInput label="Max tokens" value={numberValue(config.max_tokens, 512)} onChange={(max_tokens) => updateConfig({ max_tokens: Number(max_tokens || 0) })} />
            </div>
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
            <TextInput label="Limit" value={numberValue(config.limit, 5)} onChange={(limit) => updateConfig({ limit: Number(limit || 5) })} />
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
            <TextArea label="Arguments JSON" rows={5} value={stringValue(config.arguments)} onChange={(argumentsValue) => updateConfig({ arguments: argumentsValue })} />
          </>
        ) : null}

        {type === "condition" ? (
          <>
            <TextInput label="Expression" value={stringValue(config.expression)} onChange={(expression) => updateConfig({ expression })} />
            <div className="grid grid-cols-2 gap-2">
              <TextInput label="True label" value={stringValue(config.true_label)} onChange={(true_label) => updateConfig({ true_label })} />
              <TextInput label="False label" value={stringValue(config.false_label)} onChange={(false_label) => updateConfig({ false_label })} />
            </div>
            <SchemaNotice />
          </>
        ) : null}

        {type === "http" ? (
          <>
            <SelectInput label="Method" value={stringValue(config.method) || "GET"} onChange={(method) => updateConfig({ method })} options={["GET", "POST", "PUT", "PATCH", "DELETE"].map((method) => ({ label: method, value: method }))} />
            <TextInput label="URL" value={stringValue(config.url)} onChange={(url) => updateConfig({ url })} />
            <TextArea label="Headers JSON" rows={4} value={stringValue(config.headers)} onChange={(headers) => updateConfig({ headers })} />
            <TextArea label="Body" rows={4} value={stringValue(config.body)} onChange={(body) => updateConfig({ body })} />
            <SchemaNotice />
          </>
        ) : null}

        {type === "code" ? (
          <>
            <SelectInput label="Language" value={stringValue(config.language) || "python"} onChange={(language) => updateConfig({ language })} options={[{ label: "python", value: "python" }, { label: "javascript", value: "javascript" }]} />
            <TextArea label="Code" rows={7} value={stringValue(config.code)} onChange={(code) => updateConfig({ code })} />
            <SchemaNotice />
          </>
        ) : null}

        {type === "variable" ? (
          <>
            <TextInput label="Name" value={stringValue(config.name)} onChange={(name) => updateConfig({ name })} />
            <TextArea label="Value" rows={3} value={stringValue(config.value)} onChange={(value) => updateConfig({ value })} />
            <SchemaNotice />
          </>
        ) : null}

        {type === "template" ? (
          <>
            <TextArea label="Template" rows={6} value={stringValue(config.template)} onChange={(template) => updateConfig({ template })} />
            <SchemaNotice />
          </>
        ) : null}

        {type === "human" ? (
          <>
            <TextInput label="Title" value={stringValue(config.title)} onChange={(title) => updateConfig({ title })} />
            <TextArea label="Instructions" rows={4} value={stringValue(config.instructions)} onChange={(instructions) => updateConfig({ instructions })} />
            <SchemaNotice />
          </>
        ) : null}
      </div>
    </section>
  );
}

function SchemaNotice() {
  return (
    <div className="rounded-lg border border-[#fde68a] bg-[#fffbeb] px-3 py-2 text-xs leading-5 text-[#854d0e]">
      This node is saved in the workflow DSL, but the backend executor is not wired yet.
    </div>
  );
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
