import JsonDisclosure from "@/components/runs/JsonDisclosure";
import RunStatusBadge from "@/components/runs/RunStatusBadge";
import type { NodeRun } from "@/types/workflow";

export function formatElapsed(milliseconds: number): string {
  if (!Number.isFinite(milliseconds) || milliseconds < 0) return "—";
  if (milliseconds < 1000) return `${milliseconds} 毫秒`;
  return `${Number((milliseconds / 1000).toFixed(2))} 秒`;
}

export default function NodeRunCard({ nodeRun }: { nodeRun: NodeRun }) {
  return (
    <article className="space-y-3 rounded-lg border border-[#dfe4ee] bg-white p-4 text-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="font-medium text-[#172033]">{nodeRun.node_id || "—"}</div>
          <div className="mt-1 text-xs text-[#667085]">{nodeRun.node_type || "—"}</div>
        </div>
        <RunStatusBadge status={nodeRun.status} />
      </div>

      {nodeRun.error_message ? (
        <div className="rounded-lg bg-red-50 p-2 text-xs leading-5 text-red-700" role="alert">
          {nodeRun.error_message}
        </div>
      ) : null}

      <div className="text-xs text-[#475467]">Duration: {formatElapsed(nodeRun.elapsed_ms)}</div>
      <JsonDisclosure label="Input" value={nodeRun.input_data} />
      <JsonDisclosure label="Output" value={nodeRun.output_data} />
    </article>
  );
}
