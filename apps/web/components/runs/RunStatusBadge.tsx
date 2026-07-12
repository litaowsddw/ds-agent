const STATUS_PRESENTATION: Record<string, { label: string; classes: string; tone: string }> = {
  pending: { label: "Pending", classes: "bg-slate-100 text-slate-700", tone: "neutral" },
  running: { label: "Running", classes: "bg-blue-50 text-blue-700", tone: "info" },
  succeeded: { label: "Succeeded", classes: "bg-emerald-50 text-emerald-700", tone: "success" },
  failed: { label: "Failed", classes: "bg-red-50 text-red-700", tone: "danger" },
  cancelled: { label: "Cancelled", classes: "bg-amber-50 text-amber-700", tone: "warning" },
};

interface RunStatusBadgeProps {
  status?: string | null;
}

export default function RunStatusBadge({ status }: RunStatusBadgeProps) {
  const normalizedStatus = status?.trim() ?? "";
  const presentation = STATUS_PRESENTATION[normalizedStatus] ?? {
    label: normalizedStatus || "—",
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
