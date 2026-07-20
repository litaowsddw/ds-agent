import type { WorkflowDefinition, WorkflowTemplate } from "@/types/workflow";

/**
 * Templates are intentionally executable with the current Workflow runtime:
 * only Start, LLM, RAG, and End are used.  Tenant-bound configuration remains
 * empty so copying a template cannot accidentally inherit another workflow's
 * model, knowledge base, or tool permissions.
 */
export const WORKFLOW_TEMPLATES: WorkflowTemplate[] = [
  {
    id: "customer-support",
    name: "客户支持助手",
    description: "把每条客户咨询转成清晰、可执行且可直接发送的答复。",
    category: "客户体验",
    suggestedName: "客户支持助手",
    setup: ["选择一个模型供应商和模型", "按品牌语气调整系统提示词"],
    definition: {
      version: "1.0",
      nodes: [
        { id: "start", type: "start", config: {} },
        {
          id: "support_reply",
          type: "llm",
          config: {
            display_name: "生成客户答复",
            display_description: "将用户咨询整理为可直接发送的支持回复",
            provider: "",
            model: "",
            system_prompt:
              "你是一名专业、可靠的客户支持专员。先直接解决用户问题；信息不足时，明确说明已知情况，并只提出一个最关键的澄清问题。不要编造政策、价格或承诺。",
            prompt: "请处理本次客户咨询，并用简短、友好的结构化答复输出下一步建议。",
            temperature: 0.2,
            max_tokens: 800,
          },
        },
        { id: "end", type: "end", config: {} },
      ],
      edges: [
        { source: "start", target: "support_reply" },
        { source: "support_reply", target: "end" },
      ],
    },
  },
  {
    id: "knowledge-answer",
    name: "知识库问答",
    description: "先检索组织知识，再由模型生成带边界的可信回答。",
    category: "知识服务",
    suggestedName: "知识库问答",
    setup: ["选择一个知识库", "选择一个模型供应商和模型", "确认无资料时的回复策略"],
    definition: {
      version: "1.0",
      nodes: [
        { id: "start", type: "start", config: {} },
        {
          id: "retrieve_knowledge",
          type: "rag",
          config: {
            display_name: "检索知识库",
            display_description: "使用用户问题在选定知识库中检索证据",
            kb_id: "",
            query_template: "{{input.text}}",
            limit: 5,
          },
        },
        {
          id: "grounded_answer",
          type: "llm",
          config: {
            display_name: "基于证据回答",
            display_description: "结合检索结果回答，并在资料不足时明确说明",
            provider: "",
            model: "",
            system_prompt:
              "你是严谨的知识库助手。仅根据上游检索到的资料回答；资料不足、冲突或没有命中时，要明确说明，不得补造事实。回答要给出可核对的要点。",
            prompt: "请结合本次用户问题和上游检索结果，给出准确、简明的答复。",
            temperature: 0.1,
            max_tokens: 1000,
          },
        },
        { id: "end", type: "end", config: {} },
      ],
      edges: [
        { source: "start", target: "retrieve_knowledge" },
        { source: "retrieve_knowledge", target: "grounded_answer" },
        { source: "grounded_answer", target: "end" },
      ],
    },
  },
  {
    id: "content-polish",
    name: "内容润色与改写",
    description: "将用户的原始文本整理为目标明确、可发布的专业内容。",
    category: "内容生产",
    suggestedName: "内容润色与改写",
    setup: ["选择一个模型供应商和模型", "在系统提示词中设定品牌、受众和禁用表达"],
    definition: {
      version: "1.0",
      nodes: [
        { id: "start", type: "start", config: {} },
        {
          id: "polish_content",
          type: "llm",
          config: {
            display_name: "润色内容",
            display_description: "保留事实并优化表达、结构和可读性",
            provider: "",
            model: "",
            system_prompt:
              "你是一名资深内容编辑。保留用户提供的事实与立场，不补造信息；提升清晰度、结构和可读性。若原文目标不明确，先说明你采用的合理假设。",
            prompt: "请把本次用户提供的内容改写为专业、易读、可直接发布的版本，并在末尾列出不超过三项主要调整。",
            temperature: 0.4,
            max_tokens: 1200,
          },
        },
        { id: "end", type: "end", config: {} },
      ],
      edges: [
        { source: "start", target: "polish_content" },
        { source: "polish_content", target: "end" },
      ],
    },
  },
];

/** Return an isolated DSL copy so edits to a canvas never mutate the catalogue. */
export function cloneWorkflowDefinition(definition: WorkflowDefinition): WorkflowDefinition {
  return JSON.parse(JSON.stringify(definition)) as WorkflowDefinition;
}
