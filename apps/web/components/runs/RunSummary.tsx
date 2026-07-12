import JsonDisclosure from "@/components/runs/JsonDisclosure";
import RunStatusBadge from "@/components/runs/RunStatusBadge";
import type { WorkflowRun } from "@/types/workflow";

interface RunSummaryProps {
  run: WorkflowRun;
  workflowLabel?: string;
}

function displayValue(value?: string | null) {
  return value?.trim() || "—";
}

function displayTime(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString("zh-CN");
}

export default function RunSummary({ run, workflowLabel }: RunSummaryProps) {
  return (
    <div className="space-y-4">
      {run.error_message ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700" role="alert">
          <div className="font-medium">运行失败</div>
          <div className="mt-1 break-words text-xs leading-5">{run.error_message}</div>
        </div>
      ) : null}

      <div className="grid gap-3 rounded-lg border border-[#dfe4ee] bg-white p-4 sm:grid-cols-2 lg:grid-cols-3">
        <SummaryField label="状态"><RunStatusBadge status={run.status} /></SummaryField>
        <SummaryField label="Workflow">{displayValue(workflowLabel || run.workflow_id)}</SummaryField>
        <SummaryField label="版本">{displayValue(run.version_id)}</SummaryField>
        <SummaryField label="运行 ID">{displayValue(run.run_id)}</SummaryField>
        <SummaryField label="创建时间">{displayTime(run.created_at)}</SummaryField>
        <SummaryField label="更新时间">{displayTime(run.updated_at)}</SummaryField>
      </div>

      <JsonDisclosure label="输出" value={run.output_data} />
    </div>
  );
}

function SummaryField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="text-xs text-[#667085]">{label}</div>
      <div className="mt-1 break-words text-sm font-medium text-[#172033]">{children}</div>
    </div>
  );
}
