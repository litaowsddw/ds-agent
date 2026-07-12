import Link from "next/link";
import { Bot } from "lucide-react";

export default function AgentRequired({ description }: { description?: string }) {
  return (
    <div className="flex min-h-[320px] items-center justify-center">
      <div className="w-full max-w-xl rounded-lg border border-[#dfe4ee] bg-white px-6 py-8 text-center shadow-sm">
        <div className="mx-auto grid h-12 w-12 place-items-center rounded-lg bg-[#eef4ff] text-[#2f6feb]">
          <Bot size={22} />
        </div>
        <h2 className="mt-4 text-base font-semibold text-[#172033]">请选择或创建 Agent</h2>
        <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-[#667085]">
          {description ?? "当前页面需要 Agent 上下文。请在顶部选择已有 Agent，或前往 Agents 页面创建一个。"}
        </p>
        <Link
          className="mt-5 inline-flex h-9 items-center justify-center rounded-lg bg-[#2f6feb] px-4 text-sm font-medium text-white transition hover:bg-[#255dc7]"
          href="/agents"
        >
          前往 Agents
        </Link>
      </div>
    </div>
  );
}
