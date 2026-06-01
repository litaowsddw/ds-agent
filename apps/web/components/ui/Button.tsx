/** 按钮组件 - PrimaryButton, SecondaryButton */

"use client";

import { Loader2, Plus } from "lucide-react";

export function PrimaryButton({
  busy,
  label,
  onClick,
  icon,
}: {
  busy?: boolean;
  label: string;
  onClick: () => void;
  icon?: React.ReactNode;
}) {
  return (
    <button
      className="mt-3 inline-flex items-center gap-2 rounded-lg bg-[#2f6feb] px-4 py-2 text-sm font-medium text-white transition hover:bg-[#255dc7] disabled:bg-[#9bb8f5] disabled:hover:bg-[#9bb8f5]"
      disabled={busy}
      onClick={onClick}
      type="button"
    >
      {busy ? <Loader2 className="animate-spin" size={15} /> : (icon ?? <Plus size={15} />)}
      {label}
    </button>
  );
}

export function SecondaryButton({
  label,
  onClick,
}: {
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      className="rounded-lg border border-[#cfd7e6] bg-white px-3 py-2 text-sm font-medium text-[#172033] transition hover:border-[#2f6feb]"
      onClick={onClick}
      type="button"
    >
      {label}
    </button>
  );
}
