const STATUS_PRESENTATION: Record<string, { label: string; classes: string; tone: string }> = {
  pending: { label: "待处理", classes: "bg-amber-50 text-amber-700", tone: "pending" },
  running: { label: "运行中", classes: "bg-blue-50 text-blue-700", tone: "info" },
  succeeded: { label: "成功", classes: "bg-emerald-50 text-emerald-700", tone: "success" },
  failed: { label: "失败", classes: "bg-red-50 text-red-700", tone: "danger" },
  canceled: { label: "已取消", classes: "bg-orange-50 text-orange-700", tone: "warning" },
  timeout: { label: "超时", classes: "bg-red-50 text-red-700", tone: "danger" },
  skipped: { label: "已跳过", classes: "bg-violet-50 text-violet-700", tone: "skipped" },
};

interface RunStatusBadgeProps {
  status?: string | null;
}

export function getRunStatusLabel(status?: string | null) {
  const normalizedStatus = status?.trim() ?? "";
  return STATUS_PRESENTATION[normalizedStatus]?.label ?? (normalizedStatus || "—");
}

export default function RunStatusBadge({ status }: RunStatusBadgeProps) {
  const normalizedStatus = status?.trim() ?? "";
  const presentation = STATUS_PRESENTATION[normalizedStatus] ?? {
    label: getRunStatusLabel(normalizedStatus),
    classes: "bg-slate-100 text-slate-600",
    tone: "neutral",
  };

  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${presentation.classes}`}
      data-tone={presentation.tone}
    >
      {presentation.label}
    </span>
  );
}
