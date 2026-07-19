"use client";

import { useState, type ReactNode } from "react";
import { useChatStore } from "@/stores/chat";

type ContextUsage = {
  inputTokens: number | null;
  outputTokens: number;
  contextTokens: number | null;
  outputTokenStatus: "official_tokenizer" | "characters_divided_by_4" | "provider_final" | "unavailable";
  cacheReadInputTokens: number | null;
  limitTokens: number;
  usageStatus: "provider_final" | "unavailable";
  preflightInputTokens: number | null;
  stablePrefixTokens: number | null;
  tokenizerStatus: "official_tokenizer" | "official_total_only" | "characters_divided_by_4";
  tokenizer: string | null;
  promptBreakdown: Array<{ key: string; label: string; tokens: number }>;
  calibrationStatus?: "estimated" | "partially_calibrated" | "provider_final" | "unavailable";
  activeWorkflowNodeId?: string | null;
};

export default function ChatComposer({
  disabled,
  retryDisabled = disabled,
  onSend,
  onRetry,
  retryBlockedMessage = "",
  contextUsage,
  children,
}: {
  disabled: boolean;
  retryDisabled?: boolean;
  onSend: (message: string) => void | Promise<void>;
  onRetry?: () => void | Promise<void>;
  retryBlockedMessage?: string;
  contextUsage?: ContextUsage;
  children?: ReactNode;
}) {
  const [input, setInput] = useState("");
  const liveContextUsage = useChatStore((state) => state.actualContextUsage);
  const inputContextTokens = contextUsage?.usageStatus === "provider_final" && contextUsage.inputTokens !== null
    ? contextUsage.inputTokens
    : contextUsage?.preflightInputTokens ?? null;
  const displayedTokens = contextUsage?.contextTokens ?? (
    inputContextTokens !== null && inputContextTokens !== undefined
      ? inputContextTokens + (contextUsage?.outputTokens ?? 0)
      : null
  );
  const contextPercent = displayedTokens !== null && displayedTokens !== undefined && (contextUsage?.limitTokens ?? 0) > 0
    ? Math.round((displayedTokens / contextUsage!.limitTokens) * 100)
    : null;
  const contextSummary = displayedTokens !== null
    ? `${contextUsage?.tokenizerStatus === "characters_divided_by_4" ? "上下文估算" : "上下文"} ${displayedTokens.toLocaleString()} / ${contextUsage?.limitTokens.toLocaleString()} · ${contextPercent}%`
    : "上下文：正在组装";
  const hasActualUsageEvent = contextUsage?.calibrationStatus !== undefined || liveContextUsage !== null;
  const calibrationStatus = contextUsage?.calibrationStatus
    ?? liveContextUsage?.calibrationStatus
    ?? (contextUsage?.usageStatus === "provider_final" ? "provider_final" : "unavailable");
  const activeWorkflowNodeId = contextUsage?.activeWorkflowNodeId ?? liveContextUsage?.activeWorkflowNodeId ?? null;
  const qualityLabel = contextUsage && hasActualUsageEvent ? {
    estimated: "实时估算",
    partially_calibrated: "部分已校准",
    provider_final: "Provider 已校准",
    unavailable: "Provider 未提供用量",
  }[calibrationStatus] : null;
  const inputDetail = inputContextTokens === null || inputContextTokens === undefined
    ? "未提供"
    : inputContextTokens.toLocaleString();
  const outputDetail = calibrationStatus === "unavailable"
    ? "未提供"
    : contextUsage?.outputTokens.toLocaleString();

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
        <div className="flex shrink-0 items-center gap-2">
          {contextUsage ? (
            <div className="relative flex shrink-0 items-center gap-2 whitespace-nowrap text-xs text-[#667085]">
              <span
                aria-label="当前上下文占比"
                title="请求前会先计算已知完整上下文；Skill 路由完成后会自动校正。流式过程中实时累加输出，结束后以供应商 usage 校准。"
              >
                {contextSummary}
              </span>
              <span>{qualityLabel}</span>
              {activeWorkflowNodeId ? <span>当前节点：{activeWorkflowNodeId}</span> : null}
              {(displayedTokens !== null || contextUsage.promptBreakdown.length > 0 || contextUsage.cacheReadInputTokens !== null) ? (
                <details className="relative">
                  <summary className="cursor-pointer text-[#2f6feb]">详情</summary>
                  <div className="absolute bottom-7 right-0 z-20 w-80 rounded-lg border border-[#dfe4ee] bg-white p-3 text-left shadow-lg">
                    <div className="mb-2 font-medium text-[#172033]">当前输入上下文构成</div>
                    <div className="mb-2 text-[#667085]">
                      输入 {inputDetail} · 输出 {outputDetail}{contextUsage.outputTokenStatus === "provider_final" ? "（供应商已校准）" : "（流式累计）"}
                    </div>
                    {contextUsage.cacheReadInputTokens !== null ? (
                      <div className="mb-2 text-[#667085]">供应商实际缓存命中 {contextUsage.cacheReadInputTokens.toLocaleString()}</div>
                    ) : null}
                    {contextUsage.stablePrefixTokens !== null ? (
                      <div className="mb-2 text-[#667085]">稳定前缀候选 {contextUsage.stablePrefixTokens.toLocaleString()}（不等于实际命中）</div>
                    ) : null}
                    <div className="mb-2 text-[#667085]">
                      {contextUsage.tokenizerStatus === "characters_divided_by_4"
                        ? "该模型未接入 tokenizer，输入与流式输出按字符÷4 估算；结束后仅用供应商 usage 做计费核对。"
                        : "输入按最终 native messages 与 chat template 计算；流式输出实时累计，结束后由供应商 usage 校准。"}
                    </div>
                    {inputContextTokens && contextUsage.promptBreakdown.length > 0 ? (
                      <>
                        <div className="mb-2 flex h-2 overflow-hidden rounded-full bg-[#eef2f6]">
                          {contextUsage.promptBreakdown.map((section, index) => (
                            <span
                              key={section.key}
                              className={["bg-[#2f6feb]", "bg-[#7c3aed]", "bg-[#0ea5e9]", "bg-[#f59e0b]", "bg-[#10b981]", "bg-[#64748b]"][index % 6]}
                              style={{ width: `${Math.round((section.tokens / inputContextTokens) * 100)}%` }}
                            />
                          ))}
                        </div>
                        <div className="space-y-1">
                          {contextUsage.promptBreakdown.map((section) => (
                            <div key={section.key} className="flex items-center justify-between gap-3">
                              <span className="truncate">{section.label}</span>
                              <span>{section.tokens.toLocaleString()} · {Math.round((section.tokens / inputContextTokens) * 100)}%</span>
                            </div>
                          ))}
                        </div>
                      </>
                    ) : null}
                  </div>
                </details>
              ) : null}
            </div>
          ) : null}
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
    </div>
  );
}
