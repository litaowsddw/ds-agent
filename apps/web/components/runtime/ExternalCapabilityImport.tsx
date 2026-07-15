"use client";

import { Download, KeyRound, PlugZap } from "lucide-react";
import { showToast } from "@/components/layout/AppLayout";
import { PrimaryButton } from "@/components/ui/Button";
import { TextInput } from "@/components/ui/Form";
import { useRuntimeStore } from "@/stores/runtime";
import { useWorkspaceStore } from "@/stores/workspace";

/**
 * Imports reviewed third-party capabilities and binds them to the selected Agent.
 * The backend discovers MCP tools and stores credentials encrypted; this client
 * only submits the connection details and never displays secrets after import.
 */
export default function ExternalCapabilityImport() {
  const workspace = useWorkspaceStore((state) => state.workspace);
  const selectedAgentId = useWorkspaceStore((state) => state.selectedAgentId);
  const busy = useWorkspaceStore((state) => state.busy);
  const mcpImportForm = useRuntimeStore((state) => state.mcpImportForm);
  const skillImportUrl = useRuntimeStore((state) => state.skillImportUrl);
  const setMcpImportForm = useRuntimeStore((state) => state.setMcpImportForm);
  const setSkillImportUrl = useRuntimeStore((state) => state.setSkillImportUrl);
  const importMcpServer = useRuntimeStore((state) => state.importMcpServer);
  const importGithubSkill = useRuntimeStore((state) => state.importGithubSkill);

  const requireAgent = () => {
    if (!workspace || !selectedAgentId) {
      throw new Error("请先创建或选择要绑定能力的 Agent");
    }
    return { workspace, agentId: selectedAgentId };
  };

  return (
    <div className="space-y-5">
      <div>
        <div className="mb-1 flex items-center gap-2 text-sm font-semibold text-[#172033]">
          <PlugZap size={16} />
          外部 MCP 服务
        </div>
        <p className="text-xs leading-5 text-[#667085]">
          输入服务地址即可自动发现工具，并只绑定到当前 Agent；不需要手工填写单个 Tool。
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <TextInput
          label="服务名称"
          placeholder="例如：GitHub MCP"
          value={mcpImportForm.name}
          onChange={(name) => setMcpImportForm({ ...mcpImportForm, name })}
        />
        <TextInput
          label="Streamable HTTP URL"
          placeholder="https://mcp.example.com/mcp"
          value={mcpImportForm.url}
          onChange={(url) => setMcpImportForm({ ...mcpImportForm, url })}
        />
      </div>
      <details className="rounded-lg border border-[#dfe4ee] bg-[#f8fafc] px-3 py-2">
        <summary className="flex cursor-pointer items-center gap-2 text-xs font-medium text-[#344054]">
          <KeyRound size={14} /> 可选认证信息
        </summary>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <TextInput
            label="Bearer Token"
            type="password"
            value={mcpImportForm.bearerToken}
            onChange={(bearerToken) => setMcpImportForm({ ...mcpImportForm, bearerToken })}
          />
          <TextInput
            label="API Key"
            type="password"
            value={mcpImportForm.apiKey}
            onChange={(apiKey) => setMcpImportForm({ ...mcpImportForm, apiKey })}
          />
        </div>
      </details>
      <PrimaryButton
        busy={busy}
        label="发现工具并绑定当前 Agent"
        onClick={async () => {
          try {
            const { workspace: currentWorkspace, agentId } = requireAgent();
            await importMcpServer(currentWorkspace.userId, agentId);
            showToast("success", "MCP 工具已发现并绑定到当前 Agent。");
          } catch (error) {
            showToast("error", error instanceof Error ? error.message : "导入 MCP 服务失败。");
          }
        }}
      />

      <div className="border-t border-[#e7ebf3] pt-5">
        <div className="mb-1 flex items-center gap-2 text-sm font-semibold text-[#172033]">
          <Download size={16} />
          从 GitHub 导入 Skill
        </div>
        <p className="mb-3 text-xs leading-5 text-[#667085]">
          粘贴公开仓库中单个 <code>SKILL.md</code> 的 GitHub 链接，审核后将其绑定到当前 Agent。
        </p>
        <TextInput
          label="GitHub SKILL.md URL"
          placeholder="https://github.com/owner/repo/blob/main/SKILL.md"
          value={skillImportUrl}
          onChange={setSkillImportUrl}
        />
        <div className="mt-3">
          <PrimaryButton
            busy={busy}
            label="导入 Skill 并绑定当前 Agent"
            onClick={async () => {
              try {
                const { workspace: currentWorkspace, agentId } = requireAgent();
                await importGithubSkill(currentWorkspace.userId, currentWorkspace.orgId, agentId);
                showToast("success", "Skill 已导入并绑定到当前 Agent。");
              } catch (error) {
                showToast("error", error instanceof Error ? error.message : "导入 Skill 失败。");
              }
            }}
          />
        </div>
      </div>
    </div>
  );
}
