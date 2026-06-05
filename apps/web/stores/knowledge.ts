/** Knowledge 状态管理。 */

import { create } from "zustand";
import type { ChunkItem, DocumentItem, KnowledgeBaseItem } from "@/types/knowledge";
import { apiFormRequest, apiRequest } from "@/lib/api";

interface KnowledgeStore {
  knowledgeBases: KnowledgeBaseItem[];
  selectedKbId: string;
  kbDocuments: DocumentItem[];
  searchResults: ChunkItem[];

  kbForm: { name: string; description: string };
  docForm: { title: string; content: string };
  searchQuery: string;

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

  kbForm: { name: "", description: "" },
  docForm: { title: "", content: "" },
  searchQuery: "",

  setKbForm: (form) => set({ kbForm: form }),
  setDocForm: (form) => set({ docForm: form }),
  setSearchQuery: (query) => set({ searchQuery: query }),
  setSelectedKbId: (id) => set({ selectedKbId: id }),

  createKnowledgeBase: async (actorUserId, orgId) => {
    const { kbForm } = get();
    if (!kbForm.name.trim()) {
      throw new Error("请填写知识库名称");
    }
    const kb = await apiRequest<KnowledgeBaseItem>("/knowledge", {
      method: "POST",
      body: {
        actor_user_id: actorUserId,
        org_id: orgId,
        name: kbForm.name,
        description: kbForm.description,
      },
    });
    set((state) => ({
      knowledgeBases: [kb, ...state.knowledgeBases],
      selectedKbId: kb.kb_id,
    }));
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
      if (!docForm.title.trim() || !docForm.content.trim()) {
        throw new Error("请填写文档标题和内容，或选择一个文件上传");
      }
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
    set((state) => ({ kbDocuments: [doc, ...state.kbDocuments] }));
  },

  searchKnowledge: async (actorUserId, kbId, query) => {
    if (!query.trim()) {
      throw new Error("请填写检索关键词");
    }
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
    set((state) => ({
      knowledgeBases,
      selectedKbId: state.selectedKbId || knowledgeBases[0]?.kb_id || "",
    }));
  },

  refreshDocuments: async (kbId, actorUserId) => {
    const kbDocuments = await apiRequest<DocumentItem[]>(
      `/knowledge/${kbId}/documents?actor_user_id=${actorUserId}`
    );
    set({ kbDocuments });
  },
}));
