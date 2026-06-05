import BaseNode from "./BaseNode";

export const nodeTypes = {
  start: BaseNode,
  end: BaseNode,
  llm: BaseNode,
  rag: BaseNode,
  tool: BaseNode,
  condition: BaseNode,
  http: BaseNode,
  code: BaseNode,
  variable: BaseNode,
  template: BaseNode,
  human: BaseNode,
};
