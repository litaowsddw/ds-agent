/** Knowledge 管理页面。

管理知识库、文档上传、RAG 检索。
 */

"use client";

import { useEffect, useState } from "react";
import { Activity, Bot, Database, FileText, MessageSquare, Upload } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useKnowledgeStore } from "@/stores/knowledge";
import { useRuntimeStore } from "@/stores/runtime";
import { showToast } from "@/components/layout/AppLayout";
import Panel from "@/components/ui/Panel";
import { TextInput, TextArea } from "@/components/ui/Form";
import { PrimaryButton } from "@/components/ui/Button";
import { Metric, EmptyText } from "@/components/ui/DataDisplay";

export default function KnowledgePage() {
  const workspace = useWorkspaceStore((s) => s.workspace);
  const busy = useWorkspaceStore((s) => s.busy);

  const knowledgeBases = useKnowledgeStore((s) => s.knowledgeBases);
  const selectedKbId = useKnowledgeStore((s) => s.selectedKbId);
  const kbDocuments = useKnowledgeStore((s) => s.kbDocuments);
  const searchResults = useKnowledgeStore((s) => s.searchResults);
  const kbForm = useKnowledgeStore((s) => s.kbForm);
  const docForm = useKnowledgeStore((s) => s.docForm);
  const searchQuery = useKnowledgeStore((s) => s.searchQuery);

  const setKbForm = useKnowledgeStore((s) => s.setKbForm);
  const setDocForm = useKnowledgeStore((s) => s.setDocForm);
  const setSearchQuery = useKnowledgeStore((s) => s.setSearchQuery);
  const setSelectedKbId = useKnowledgeStore((s) => s.setSelectedKbId);
  const createKnowledgeBase = useKnowledgeStore((s) => s.createKnowledgeBase);
  const uploadDocument = useKnowledgeStore((s) => s.uploadDocument);
  const searchKnowledge = useKnowledgeStore((s) => s.searchKnowledge);
  const refreshKbs = useKnowledgeStore((s) => s.refreshKbs);
  const refreshDocuments = useKnowledgeStore((s) => s.refreshDocuments);

  const cacheStats = useRuntimeStore((s) => s.cacheStats);
  const backgroundAgents = useRuntimeStore((s) => s.backgroundAgents);

  const [docFile, setDocFile] = useState<File | null>(null);

  useEffect(() => {
    if (workspace) {
      void refreshKbs(workspace.orgId, workspace.userId);
    }
  }, [workspace, refreshKbs]);

  useEffect(() => {
    if (selectedKbId && workspace) {
      void refreshDocuments(selectedKbId, workspace.userId);
    }
  }, [selectedKbId, workspace, refreshDocuments]);

  if (!workspace) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-[#667085]">
        请先在首页创建工作空间
      </div>
    );
  }

  return (
    <div className="grid gap-6 xl:grid-cols-2">
      {/* 创建知识库 */}
      <Panel title="创建知识库" icon={<Database size={17} />}>
        <TextInput
          label="名称"
          value={kbForm.name}
          onChange={(name) => setKbForm({ ...kbForm, name })}
        />
        <TextInput
          label="描述"
          value={kbForm.description}
          onChange={(description) => setKbForm({ ...kbForm, description })}
        />
        <PrimaryButton
          busy={busy}
          label="创建知识库"
          onClick={async () => {
            try {
              await createKnowledgeBase(workspace.userId, workspace.orgId);
              showToast("success", "知识库已创建。");
            } catch (error) {
              showToast("error", error instanceof Error ? error.message : "创建知识库失败。");
            }
          }}
        />
        <div className="mt-3 space-y-2">
          {knowledgeBases.map((kb) => (
            <button
              key={kb.kb_id}
              className={`w-full rounded-lg border p-3 text-left text-sm transition ${
                selectedKbId === kb.kb_id
                  ? "border-[#2f6feb] bg-[#eef4ff]"
                  : "border-[#dfe4ee] bg-white hover:border-[#93c5fd]"
              }`}
              onClick={() => setSelectedKbId(kb.kb_id)}
              type="button"
            >
              <div className="font-medium text-[#172033]">{kb.name}</div>
              <div className="mt-1 text-xs text-[#667085]">{kb.description}</div>
            </button>
          ))}
        </div>
      </Panel>

      {/* 上传文档 */}
      <Panel title="上传文档" icon={<FileText size={17} />}>
        <label className="block text-sm">
          <span className="mb-1 block text-xs font-medium text-[#667085]">
            上传文件（txt / md / pdf / docx）
          </span>
          <input
            accept=".txt,.md,.markdown,.pdf,.docx,.csv,.json,.log"
            className="w-full rounded-lg border border-[#dfe4ee] bg-white px-3 py-2 text-sm outline-none file:mr-3 file:rounded-lg file:border-0 file:bg-[#eef4ff] file:px-3 file:py-1.5 file:text-[#2f6feb]"
            onChange={(e) => setDocFile(e.target.files?.[0] ?? null)}
            type="file"
          />
        </label>
        {docFile && <p className="mt-2 text-xs text-[#667085]">已选择：{docFile.name}</p>}
        <TextInput
          label="文档标题"
          value={docForm.title}
          onChange={(title) => setDocForm({ ...docForm, title })}
        />
        <TextArea
          label="文档内容"
          rows={4}
          value={docForm.content}
          onChange={(content) => setDocForm({ ...docForm, content })}
        />
        <PrimaryButton
          busy={busy}
          label="上传文档"
          onClick={async () => {
            try {
              if (!selectedKbId) throw new Error("请先选择知识库。");
              await uploadDocument(workspace.userId, selectedKbId, docFile);
              setDocFile(null);
              showToast("success", "文档已上传。");
            } catch (error) {
              showToast("error", error instanceof Error ? error.message : "上传文档失败。");
            }
          }}
        />
        <div className="mt-3 space-y-2">
          {kbDocuments.map((doc) => (
            <div
              key={doc.document_id}
              className="rounded-lg border border-[#dfe4ee] bg-[#f8fafc] px-3 py-2 text-sm text-[#344054]"
            >
              {doc.title} · {doc.status}
            </div>
          ))}
        </div>
      </Panel>

      {/* RAG 检索 */}
      <Panel title="RAG 检索" icon={<MessageSquare size={17} />}>
        <TextInput label="检索关键词" value={searchQuery} onChange={setSearchQuery} />
        <PrimaryButton
          busy={busy}
          label="检索"
          onClick={async () => {
            try {
              if (!selectedKbId) throw new Error("请先选择知识库。");
              await searchKnowledge(workspace.userId, selectedKbId, searchQuery);
              showToast("success", `检索到 ${searchResults.length} 个结果。`);
            } catch (error) {
              showToast("error", error instanceof Error ? error.message : "检索失败。");
            }
          }}
        />
        {searchResults.length > 0 ? (
          <div className="mt-3 space-y-2">
            {searchResults.map((chunk) => (
              <div
                key={chunk.chunk_id}
                className="rounded-lg border border-[#dfe4ee] bg-[#f8fafc] p-3 text-sm"
              >
                <div className="text-xs text-[#667085]">
                  Chunk #{chunk.sequence} · {chunk.estimated_tokens} tokens
                </div>
                <div className="mt-1 text-xs text-[#98a2b3]">
                  {chunk.vector_indexed ? "vector indexed" : "keyword fallback"}
                  {chunk.similarity_score !== null
                    ? ` / score ${chunk.similarity_score.toFixed(3)}`
                    : ""}
                </div>
                <div className="mt-1 leading-6 text-[#344054]">{chunk.content}</div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyText text="暂无检索结果。" />
        )}
      </Panel>

      {/* 缓存统计 + 后台 Agent */}
      <div className="space-y-6">
        <Panel title="缓存统计" icon={<Activity size={17} />}>
          {cacheStats ? (
            <div className="grid grid-cols-2 gap-2">
              <Metric label="缓存大小" value={cacheStats.size} />
              <Metric label="最大容量" value={cacheStats.max_size} />
              <Metric label="命中次数" value={cacheStats.total_hits} />
              <Metric label="未命中次数" value={cacheStats.total_misses} />
            </div>
          ) : (
            <EmptyText text="暂无缓存数据。" />
          )}
        </Panel>

        <Panel title="后台 Agent" icon={<Bot size={17} />}>
          {backgroundAgents.length > 0 ? (
            <div className="space-y-2">
              {backgroundAgents.map((agent) => (
                <div
                  key={agent.config_id}
                  className="rounded-lg border border-[#dfe4ee] bg-[#f8fafc] p-3 text-sm"
                >
                  <div className="font-medium text-[#172033]">{agent.agent_type}</div>
                  <div className="mt-1 text-xs text-[#667085]">
                    {agent.status} · {agent.enabled ? "启用" : "已禁用"} · {agent.interval_seconds}s
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyText text="暂无后台 Agent。" />
          )}
        </Panel>
      </div>
    </div>
  );
}
