"use client";

import { Copy } from "lucide-react";
import { showToast } from "@/components/layout/AppLayout";
import type { Message } from "@/stores/chat";

export function formatChatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

export default function MessageBubble({ message }: { message: Message }) {
  const copyAnswer = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      showToast("success", "回答已复制");
    } catch {
      showToast("error", "复制失败，请手动复制");
    }
  };

  return (
    <div className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
      <div
        className={`group max-w-[80%] rounded-lg px-3 py-2 text-sm ${
          message.role === "user"
            ? "bg-[#2f6feb] text-white"
            : message.role === "system"
              ? "bg-red-50 text-red-600"
              : "bg-[#f2f4f7] text-[#172033]"
        }`}
      >
        {message.content ? <p className="whitespace-pre-wrap">{message.content}</p> : null}
        <div
          className={`mt-1.5 flex items-center gap-2 text-[11px] ${
            message.role === "user" ? "text-blue-100" : "text-[#98a2b3]"
          }`}
        >
          <time dateTime={message.created_at}>{formatChatTime(message.created_at)}</time>
          {message.role === "assistant" && message.content ? (
            <button
              aria-label="复制回答"
              className="inline-flex items-center gap-1 rounded px-1 py-0.5 hover:bg-black/5 hover:text-[#2f6feb]"
              onClick={() => void copyAnswer()}
              type="button"
            >
              <Copy size={11} />
              复制
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
