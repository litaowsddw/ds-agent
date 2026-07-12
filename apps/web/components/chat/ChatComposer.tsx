"use client";

import { useState, type ReactNode } from "react";

export default function ChatComposer({
  disabled,
  retryDisabled = disabled,
  onSend,
  onRetry,
  retryBlockedMessage = "",
  children,
}: {
  disabled: boolean;
  retryDisabled?: boolean;
  onSend: (message: string) => void | Promise<void>;
  onRetry?: () => void | Promise<void>;
  retryBlockedMessage?: string;
  children?: ReactNode;
}) {
  const [input, setInput] = useState("");

  const send = () => {
    const message = input.trim();
    if (!message || disabled) return;
    setInput("");
    void onSend(message);
  };

  return (
    <div>
      {children}
      {onRetry ? (
        <div className="mb-3 rounded-lg border border-[#fecaca] bg-red-50 px-3 py-2 text-xs text-red-700">
          <div>{retryBlockedMessage || "上次发送失败，可使用原设置重试。"}</div>
          <button
            aria-label="重试上次消息"
            className="mt-2 rounded-md border border-red-200 bg-white px-2.5 py-1 font-medium text-red-700 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={retryDisabled || Boolean(retryBlockedMessage)}
            onClick={() => void onRetry()}
            type="button"
          >
            重试上次消息
          </button>
        </div>
      ) : null}
      <div className="flex gap-2">
        <textarea
          aria-label="消息"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              send();
            }
          }}
          placeholder="输入消息…"
          rows={1}
          className="flex-1 resize-none rounded-lg border border-[#dfe4ee] bg-white px-3 py-2 text-sm text-[#172033] focus:outline-none focus:ring-2 focus:ring-[#2f6feb]"
          disabled={disabled}
        />
        <button
          onClick={send}
          disabled={disabled || !input.trim()}
          className="rounded-lg bg-[#2f6feb] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#2459c9] disabled:cursor-not-allowed disabled:opacity-50"
          type="button"
        >
          发送
        </button>
      </div>
    </div>
  );
}
