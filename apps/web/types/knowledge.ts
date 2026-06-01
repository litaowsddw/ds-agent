/** Knowledge 相关类型定义。 */

/** 知识库 */
export interface KnowledgeBaseItem {
  kb_id: string;
  org_id: string;
  name: string;
  description: string;
}

/** 文档 */
export interface DocumentItem {
  document_id: string;
  kb_id: string;
  title: string;
  status: string;
}

/** 文档块 */
export interface ChunkItem {
  chunk_id: string;
  document_id: string;
  content: string;
  sequence: number;
  estimated_tokens: number;
  embedding_model: string;
  vector_indexed: boolean;
  similarity_score: number | null;
}

/** 缓存统计 */
export interface CacheStats {
  size: number;
  max_size: number;
  total_hits: number;
  total_misses: number;
  hit_rate: number;
}

/** 知识库创建请求 */
export interface CreateKnowledgeBaseRequest {
  actor_user_id: string;
  org_id: string;
  name: string;
  description: string;
}
