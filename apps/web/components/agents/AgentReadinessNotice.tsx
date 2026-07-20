"use client";

import Link from "next/link";
import { ArrowRight, CheckCircle2, CircleAlert } from "lucide-react";
import type { Agent } from "@/types/agent";

interface AgentReadinessNoticeProps {
  modelProviderCount: number;
  agent?: Pick<Agent, "name" | "model_provider" | "model_name"> | null;
  createdAgentName?: string | null;
}

/**
 * Explains the one blocking setup step before an Agent can run in Chat.
 * Keeping this beside Agent configuration prevents a failed chat request from
 * being the first feedback a new user receives.
 */
export default function AgentReadinessNotice({
  modelProviderCount,
  agent,
  createdAgentName,
}: AgentReadinessNoticeProps) {
  if (createdAgentName) {
    return (
      <div className="rounded-xl border border-[#bbf7d0] bg-[#f0fdf4] p-4" role="status">
        <div className="flex gap-3">
          <CheckCircle2 className="mt-0.5 shrink-0 text-[#15803d]" size={18} />
          <div>
            <h2 className="text-sm font-semibold text-[#166534]">「{createdAgentName}」已可开始对话</h2>
            <p className="mt-1 text-sm leading-6 text-[#166534]">
              默认模型已绑定。你可以先直接对话，之后再为它补充 Skill、工具或 Workflow。
            </p>
            <Link
              className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-[#15803d] hover:underline"
              href="/chat"
            >
              开始对话
              <ArrowRight size={15} />
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (modelProviderCount === 0) {
    return (
      <div className="rounded-xl border border-[#fed7aa] bg-[#fff7ed] p-4" role="status">
        <div className="flex gap-3">
          <CircleAlert className="mt-0.5 shrink-0 text-[#c2410c]" size={18} />
          <div>
            <h2 className="text-sm font-semibold text-[#9a3412]">先配置模型，再创建可对话的 Agent</h2>
            <p className="mt-1 text-sm leading-6 text-[#9a3412]">
              Agent 的直接对话需要默认模型。保存模型供应商后，这里会自动带入它的默认模型。
            </p>
            <Link
              className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-[#c2410c] hover:underline"
              href="/models"
            >
              配置模型供应商
              <ArrowRight size={15} />
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (agent && (!agent.model_provider || !agent.model_name)) {
    return (
      <div className="rounded-xl border border-[#fde68a] bg-[#fffbeb] p-4" role="status">
        <div className="flex gap-3">
          <CircleAlert className="mt-0.5 shrink-0 text-[#b45309]" size={18} />
          <div>
            <h2 className="text-sm font-semibold text-[#92400e]">为「{agent.name}」绑定默认模型</h2>
            <p className="mt-1 text-sm leading-6 text-[#92400e]">
              该 Agent 已创建，但尚不能直接对话。请在下方 Agent 参数中选择模型供应商和默认模型后保存。
            </p>
          </div>
        </div>
      </div>
    );
  }

  return null;
}
