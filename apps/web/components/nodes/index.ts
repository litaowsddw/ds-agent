/** 自定义节点类型注册。

将所有自定义 React Flow 节点统一注册，供 ReactFlow 组件使用。
 */

import LLMNode from "./LLMNode";
import RAGNode from "./RAGNode";
import ToolNode from "./ToolNode";
import StartNode from "./StartNode";
import EndNode from "./EndNode";

export const nodeTypes = {
  llm: LLMNode,
  rag: RAGNode,
  tool: ToolNode,
  start: StartNode,
  end: EndNode,
};
