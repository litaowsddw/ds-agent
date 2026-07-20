/** Model provider settings page. */

"use client";

import { useEffect } from "react";
import { Bot, CheckCircle2, KeyRound, ShieldCheck, Wand2 } from "lucide-react";
import { showToast } from "@/components/layout/AppLayout";
import { PrimaryButton, SecondaryButton } from "@/components/ui/Button";
import { EmptyText, Metric } from "@/components/ui/DataDisplay";
import { TextArea, TextInput } from "@/components/ui/Form";
import Panel from "@/components/ui/Panel";
import WorkspaceRequired from "@/components/ui/WorkspaceRequired";
import { PROVIDER_PRESETS } from "@/lib/provider-presets";
import { useRuntimeStore } from "@/stores/runtime";
import { useWorkspaceStore } from "@/stores/workspace";

export default function ModelsPage() {
  const workspace = useWorkspaceStore((s) => s.workspace);
  const selectedAgentId = useWorkspaceStore((s) => s.selectedAgentId);
  const busy = useWorkspaceStore((s) => s.busy);

  const providerForm = useRuntimeStore((s) => s.providerForm);
  const modelProviders = useRuntimeStore((s) => s.modelProviders);
  const gatewayLogs = useRuntimeStore((s) => s.gatewayLogs);
  const selectedProviderKey = useRuntimeStore((s) => s.selectedProviderKey);
  const selectedModel = useRuntimeStore((s) => s.selectedModel);
  const setProviderForm = useRuntimeStore((s) => s.setProviderForm);
  const setSelectedProviderKey = useRuntimeStore((s) => s.setSelectedProviderKey);
  const setSelectedModel = useRuntimeStore((s) => s.setSelectedModel);
  const saveModelProvider = useRuntimeStore((s) => s.saveModelProvider);
  const generateGatewayPreview = useRuntimeStore((s) => s.generateGatewayPreview);
  const refreshRuntimeData = useRuntimeStore((s) => s.refreshRuntimeData);

  useEffect(() => {
    if (workspace) {
      void refreshRuntimeData(workspace.orgId, workspace.userId, selectedAgentId || undefined);
    }
  }, [workspace, selectedAgentId, refreshRuntimeData]);

  const currentWorkspace = workspace;

  if (!currentWorkspace) {
    return <WorkspaceRequired />;
  }

  const workspaceUserId = currentWorkspace.userId;
  const workspaceOrgId = currentWorkspace.orgId;
  const activeProvider = modelProviders.find((provider) => provider.provider_key === selectedProviderKey);
  const modelOptions = activeProvider?.models ?? [];

  function applyPreset(preset: (typeof PROVIDER_PRESETS)[number]) {
    setProviderForm({
      providerKey: preset.key,
      displayName: preset.label,
      baseUrl: preset.baseUrl,
      apiKey: providerForm.apiKey,
      models: preset.models,
      defaultModel: preset.defaultModel,
    });
  }

  async function handleSave() {
    try {
      await saveModelProvider(workspaceUserId, workspaceOrgId);
      showToast("success", "Provider saved");
    } catch (error) {
      showToast("error", error instanceof Error ? error.message : "Save failed");
    }
  }

  async function handleTest() {
    try {
      await generateGatewayPreview(
        workspaceUserId,
        workspaceOrgId,
        "Answer with exactly this sentence: Model provider is connected.",
        0
      );
      showToast("success", "Gateway call succeeded");
    } catch (error) {
      showToast("error", error instanceof Error ? error.message : "Gateway call failed");
    }
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[440px_minmax(0,1fr)]">
      <Panel title="Import Provider" icon={<KeyRound size={17} />}>
        <div className="mb-4 grid gap-2 sm:grid-cols-2">
          {PROVIDER_PRESETS.map((preset) => (
            <button
              key={preset.key}
              className="rounded-lg border border-[#dfe4ee] bg-[#f8fafc] px-3 py-2 text-left text-sm transition hover:border-[#2f6feb] hover:bg-white"
              onClick={() => applyPreset(preset)}
              type="button"
            >
              <div className="flex items-center gap-2 font-medium text-[#172033]">
                <Wand2 size={14} />
                {preset.label}
              </div>
              <div className="mt-1 truncate text-xs text-[#667085]">{preset.defaultModel}</div>
            </button>
          ))}
        </div>

        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <TextInput label="Provider Key" value={providerForm.providerKey} onChange={(providerKey) => setProviderForm({ ...providerForm, providerKey })} />
            <TextInput label="Display Name" value={providerForm.displayName} onChange={(displayName) => setProviderForm({ ...providerForm, displayName })} />
          </div>
          <TextInput label="Base URL" value={providerForm.baseUrl} onChange={(baseUrl) => setProviderForm({ ...providerForm, baseUrl })} />
          <TextInput label="API Key" type="password" value={providerForm.apiKey} onChange={(apiKey) => setProviderForm({ ...providerForm, apiKey })} />
          <p className="-mt-1 text-xs leading-5 text-[#667085]">
            云端供应商通常需要 API Key；本地 Ollama 或已在网关侧配置认证的服务可以留空。
          </p>
          <TextArea label="Models" rows={3} value={providerForm.models} onChange={(models) => setProviderForm({ ...providerForm, models })} />
          <TextInput label="Default Model" value={providerForm.defaultModel} onChange={(defaultModel) => setProviderForm({ ...providerForm, defaultModel })} />
          <PrimaryButton busy={busy} label="Save Provider" onClick={handleSave} />
        </div>
      </Panel>

      <div className="space-y-6">
        <Panel title="Available Models" icon={<Bot size={17} />}>
          <div className="mb-4 grid grid-cols-3 gap-3">
            <Metric label="Providers" value={modelProviders.length} />
            <Metric label="Selected" value={selectedProviderKey || "None"} />
            <Metric label="Model" value={selectedModel || "None"} />
          </div>

          <div className="space-y-2">
            {modelProviders.length === 0 ? <EmptyText text="No providers yet" /> : null}
            {modelProviders.map((provider) => (
              <button
                key={provider.provider_id}
                className={`w-full rounded-lg border p-3 text-left text-sm transition ${selectedProviderKey === provider.provider_key ? "border-[#2f6feb] bg-[#eef4ff]" : "border-[#dfe4ee] bg-white hover:border-[#93c5fd]"}`}
                onClick={() => setSelectedProviderKey(provider.provider_key)}
                type="button"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="font-medium text-[#172033]">{provider.display_name}</span>
                  <span className="shrink-0 text-xs text-[#667085]">{provider.api_key_masked || "no key"}</span>
                </div>
                <div className="mt-1 truncate text-xs text-[#667085]">{provider.base_url}</div>
                <div className="mt-1 text-xs text-[#667085]">{provider.models.join(", ")}</div>
              </button>
            ))}
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            {modelOptions.map((model) => (
              <SecondaryButton key={model} label={model} onClick={() => setSelectedModel(model)} />
            ))}
          </div>
        </Panel>

        <Panel title="Gateway Test" icon={<ShieldCheck size={17} />}>
          <PrimaryButton busy={busy} icon={<CheckCircle2 size={15} />} label="Test Selected Model" onClick={handleTest} />
          <div className="mt-4 space-y-2">
            {gatewayLogs.length === 0 ? <EmptyText text="No gateway calls yet" /> : null}
            {gatewayLogs.slice(0, 6).map((log) => (
              <div key={log.call_id} className="rounded-lg border border-[#dfe4ee] bg-[#f8fafc] p-3 text-sm">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2 font-medium text-[#172033]">
                    <CheckCircle2 size={15} />
                    {log.status}
                  </div>
                  <span className="text-xs text-[#667085]">{log.prefix_hash || "no-prefix"}</span>
                </div>
                <div className="mt-1 text-xs text-[#667085]">{log.provider}/{log.model}</div>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
