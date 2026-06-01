"use client";

import { useState, useRef, useEffect } from "react";
import { useChatStore } from "@/stores/chat";

/** Chat 面板 - 与 Agent 对话 */
export default function ChatPanel({ agentId, orgId }: { agentId: string; orgId: string }) {
  const {
    messages,
    isGenerating,
    intent,
    subtaskCount,
    sessionId,
    sendMessage,
    clearSession,
  } = useChatStore();

  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || isGenerating) return;
    const msg = input.trim();
    setInput("");
    await sendMessage(agentId, orgId, msg);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
        <div>
          <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">
            Chat with Agent
          </h3>
          {intent && (
            <p className="text-xs text-blue-500 mt-0.5">
              Intent: {intent} | Subtasks: {subtaskCount}
            </p>
          )}
        </div>
        <button
          onClick={clearSession}
          className="text-xs px-2 py-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500"
        >
          New Chat
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.length === 0 && (
          <div className="text-center text-gray-400 dark:text-gray-500 mt-8">
            <p className="text-sm">Send a message to start chatting with this Agent</p>
            <p className="text-xs mt-1">
              Supervisor Agents will plan, execute, and reflect
            </p>
          </div>
        )}
        {messages.map((msg, idx) => (
          <div
            key={msg.message_id || idx}
            className={`flex ${
              msg.role === "user" ? "justify-end" : "justify-start"
            }`}
          >
            <div
              className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
                msg.role === "user"
                  ? "bg-blue-500 text-white"
                  : msg.role === "system"
                  ? "bg-red-50 text-red-600 dark:bg-red-900/20 dark:text-red-400"
                  : "bg-gray-100 text-gray-900 dark:bg-gray-800 dark:text-gray-100"
              }`}
            >
              {msg.role === "assistant" && msg.meta_info && "intent" in msg.meta_info && (
                <div className="text-xs text-gray-400 dark:text-gray-500 mb-1">
                  <span>Intent: {(msg.meta_info as Record<string, string>).intent}</span>
                </div>
              )}
              <p className="whitespace-pre-wrap">{msg.content}</p>
            </div>
          </div>
        ))}
        {isGenerating && (
          <div className="flex justify-start">
            <div className="bg-gray-100 dark:bg-gray-800 rounded-lg px-3 py-2 text-sm text-gray-400">
              <span className="animate-pulse">Generating...</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t border-gray-200 dark:border-gray-700 px-4 py-3">
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a message..."
            rows={1}
            className="flex-1 resize-none rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-2 text-sm
              bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100
              focus:outline-none focus:ring-2 focus:ring-blue-500"
            disabled={isGenerating}
          />
          <button
            onClick={handleSend}
            disabled={isGenerating || !input.trim()}
            className="px-4 py-2 rounded-lg text-sm font-medium
              bg-blue-500 text-white hover:bg-blue-600
              disabled:opacity-50 disabled:cursor-not-allowed
              transition-colors"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
