"use client";

import Link from "next/link";
import { Network } from "lucide-react";

export default function WorkspaceRequired() {
  return (
    <div className="flex min-h-[320px] items-center justify-center">
      <div className="w-full max-w-xl rounded-lg border border-[#dfe4ee] bg-white px-6 py-8 text-center shadow-sm">
        <div className="mx-auto grid h-12 w-12 place-items-center rounded-lg bg-[#eef4ff] text-[#2f6feb]">
          <Network size={22} />
        </div>
        <h2 className="mt-4 text-base font-semibold text-[#172033]">请选择或创建工作区</h2>
        <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-[#667085]">
          当前页面需要工作区上下文。返回首页后可以恢复已有工作区，或创建新的本地用户、组织和团队。
        </p>
        <Link
          className="mt-5 inline-flex h-9 items-center justify-center rounded-lg bg-[#2f6feb] px-4 text-sm font-medium text-white transition hover:bg-[#255dc7]"
          href="/"
        >
          前往工作区设置
        </Link>
      </div>
    </div>
  );
}
