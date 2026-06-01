/** Knowledge 状态管理。

管理知识库、文档、检索等知识相关状态。
 */

import { create } from "zustand";
import type { KnowledgeBaseItem, DocumentItem, ChunkItem } from "@/types/knowledge";
import { apiRequest, apiFormRequest } from "@/lib/api";

interface KnowledgeStore {
  // 数据
  knowledgeBases: KnowledgeBaseItem[];
  selectedKbId: string;
  kbDocuments: DocumentItem[];
  searchResults: ChunkItem[];

  // 表单
  kbForm: { name: string; description: string };
  docForm: { title: string; content: string };
  searchQuery: string;

  // Actions
  setKbForm: (form: { name: string; description: string }) => void;
  setDocForm: (form: { title: string; content: string }) => void;
  setSearchQuery: (query: string) => void;
  setSelectedKbId: (id: string) => void;

  createKnowledgeBase: (actorUserId: string, orgId: string) => Promise<void>;
  uploadDocument: (actorUserId: string, kbId: string, docFile?: File | null) => Promise<void>;
  searchKnowledge: (actorUserId: string, kbId: string, query: string) => Promise<void>;
  refreshKbs: (orgId: string, actorUserId: string) => Promise<void>;
  refreshDocuments: (kbId: string, actorUserId: string) => Promise<void>;
}

export const useKnowledgeStore = create<KnowledgeStore>((set, get) => ({
  knowledgeBases: [],
  selectedKbId: "",
  kbDocuments: [],
  searchResults: [],

  kbForm: { name: "默认知识库", description: "项目文档知识库" },
  docForm: { title: "示例文档", content: "这是一段示例知识库内容，用于测试 RAG 检索功能。" },
  searchQuery: "示例",

  setKbForm: (form) => set({ kbForm: form }),
  setDocForm: (form) => set({ docForm: form }),
  setSearchQuery: (query) => set({ searchQuery: query }),
  setSelectedKbId: (id) => set({ selectedKbId: id }),

  createKnowledgeBase: async (actorUserId, orgId) => {
    const { kbForm } = get();
    const kb = await apiRequest<KnowledgeBaseItem>("/knowledge", {
      method: "POST",
      body: { actor_user_id: actorUserId, org_id: orgId, name: kbForm.name, description: kbForm.description },
    });
    set((state) => ({ knowledgeBases: [...state.knowledgeBases, kb], selectedKbId: kb.kb_id }));
  },

  uploadDocument: async (actorUserId, kbId, docFile) => {
    let doc: DocumentItem;
    if (docFile) {
      const formData = new FormData();
      formData.append("actor_user_id", actorUserId);
      formData.append("chunk_size", "800");
      formData.append("chunk_overlap", "100");
      formData.append("file", docFile);
      doc = await apiFormRequest<DocumentItem>(`/knowledge/${kbId}/documents/upload`, formData);
    } else {
      const { docForm } = get();
      doc = await apiRequest<DocumentItem>(`/knowledge/${kbId}/documents`, {
        method: "POST",
        body: {
          actor_user_id: actorUserId,
          title: docForm.title,
          content: docForm.content,
          chunk_size: 800,
          chunk_overlap: 100,
        },
      });
    }
    set((state) => ({ kbDocuments: [...state.kbDocuments, doc] }));
  },

  searchKnowledge: async (actorUserId, kbId, query) => {
    const results = await apiRequest<ChunkItem[]>(`/knowledge/${kbId}/search`, {
      method: "POST",
      body: { actor_user_id: actorUserId, query, limit: 5 },
    });
    set({ searchResults: results });
  },

  refreshKbs: async (orgId, actorUserId) => {
    const knowledgeBases = await apiRequest<KnowledgeBaseItem[]>(
      `/knowledge?org_id=${orgId}&actor_user_id=${actorUserId}`
    );
    set({ knowledgeBases });
  },

  refreshDocuments: async (kbId, actorUserId) => {
    const kbDocuments = await apiRequest<DocumentItem[]>(
      `/knowledge/${kbId}/documents?actor_user_id=${actorUserId}`
    );
    set({ kbDocuments });
  },
}));
