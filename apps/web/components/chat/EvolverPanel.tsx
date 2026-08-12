"use client";

import { useEffect } from "react";
import { useEvolverStore } from "@/stores/chat";

/** Skill Evolver 面板 - 查看 Agent 自我进化 */
export default function EvolverPanel({ agentId, orgId }: { agentId: string; orgId: string }) {
  const {
    history,
    pendingApprovals,
    analysis,
    isEvolving,
    triggerEvolution,
    loadHistory,
    loadPendingApprovals,
    approveEvolution,
    runAnalysis,
    runFeedbackLoop,
  } = useEvolverStore();

  useEffect(() => {
    loadHistory(agentId, orgId);
    loadPendingApprovals(orgId);
  }, [agentId, orgId, loadHistory, loadPendingApprovals]);

  const statusColors: Record<string, string> = {
    succeeded: "text-green-600 bg-green-50 dark:text-green-400 dark:bg-green-900/20",
    failed: "text-red-600 bg-red-50 dark:text-red-400 dark:bg-red-900/20",
    pending: "text-yellow-600 bg-yellow-50 dark:text-yellow-400 dark:bg-yellow-900/20",
    rolled_back: "text-gray-600 bg-gray-50 dark:text-gray-400 dark:bg-gray-900/20",
  };

  const actionLabels: Record<string, string> = {
    create: "Created",
    update: "Updated",
    deprecate: "Deprecated",
    merge: "Merged",
  };

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex gap-2">
        <button
          onClick={() => triggerEvolution(agentId, orgId)}
          disabled={isEvolving}
          className="px-3 py-1.5 text-sm rounded-lg bg-blue-500 text-white hover:bg-blue-600
            disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {isEvolving ? "Evolving..." : "Trigger Evolution"}
        </button>
        <button
          onClick={() => runAnalysis(agentId, orgId)}
          className="px-3 py-1.5 text-sm rounded-lg bg-gray-100 text-gray-700
            hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700
            transition-colors"
        >
          Analyze Runs
        </button>
        <button
          onClick={() => runFeedbackLoop(agentId, orgId)}
          disabled={isEvolving}
          className="px-3 py-1.5 text-sm rounded-lg bg-purple-500 text-white hover:bg-purple-600
            disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          Feedback Loop
        </button>
      </div>

      {/* Analysis Result */}
      {analysis && (
        <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
          <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
            Run Analysis
          </h4>
          <div className="grid grid-cols-3 gap-3 text-xs">
            <div>
              <span className="text-gray-500">Total Runs</span>
              <p className="font-medium text-gray-900 dark:text-gray-100">
                {Number((analysis as Record<string, unknown>).total_runs || 0)}
              </p>
            </div>
            <div>
              <span className="text-gray-500">Success Rate</span>
              <p className="font-medium text-gray-900 dark:text-gray-100">
                {(Number((analysis as Record<string, unknown>).success_rate || 0) * 100).toFixed(1)}%
              </p>
            </div>
            <div>
              <span className="text-gray-500">Opportunities</span>
              <p className="font-medium text-gray-900 dark:text-gray-100">
                {Array.isArray((analysis as Record<string, unknown>).improvement_opportunities) ? ((analysis as Record<string, unknown>).improvement_opportunities as unknown[]).length : 0}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Pending Approvals */}
      {pendingApprovals.length > 0 && (
        <div className="rounded-lg border border-yellow-200 dark:border-yellow-800 bg-yellow-50 dark:bg-yellow-900/10 p-3">
          <h4 className="text-sm font-medium text-yellow-800 dark:text-yellow-200 mb-2">
            Pending Approvals ({pendingApprovals.length})
          </h4>
          <div className="space-y-2">
            {pendingApprovals.map((record) => (
              <div
                key={record.record_id}
                className="flex items-center justify-between text-xs bg-white dark:bg-gray-800 rounded px-2 py-1.5"
              >
                <div className="flex-1">
                  <span className="font-medium">{record.skill_name}</span>
                  <span className="text-gray-500 ml-1">({record.action})</span>
                  <span className="text-gray-400 ml-1">
                    confidence: {(record.confidence * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="flex gap-1">
                  <button
                    onClick={() => approveEvolution(record.record_id, true, orgId)}
                    className="px-2 py-0.5 bg-green-500 text-white rounded hover:bg-green-600"
                  >
                    Approve
                  </button>
                  <button
                    onClick={() => approveEvolution(record.record_id, false, orgId)}
                    className="px-2 py-0.5 bg-red-500 text-white rounded hover:bg-red-600"
                  >
                    Reject
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Evolution History */}
      <div>
        <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
          Evolution History ({history.length})
        </h4>
        {history.length === 0 ? (
          <p className="text-xs text-gray-400">No evolution history yet.</p>
        ) : (
          <div className="space-y-2">
            {history.slice(0, 10).map((record) => (
              <div
                key={record.record_id}
                className="rounded-lg border border-gray-200 dark:border-gray-700 px-3 py-2"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span
                      className={`text-xs px-1.5 py-0.5 rounded ${
                        statusColors[record.status] || statusColors.pending
                      }`}
                    >
                      {record.status}
                    </span>
                    <span className="text-xs font-medium text-gray-900 dark:text-gray-100">
                      {actionLabels[record.action] || record.action}
                    </span>
                    <span className="text-xs text-gray-500">{record.skill_name}</span>
                  </div>
                  <span className="text-xs text-gray-400">
                    {(record.confidence * 100).toFixed(0)}%
                  </span>
                </div>
                {record.reasoning && (
                  <p className="text-xs text-gray-500 mt-1 line-clamp-2">
                    {record.reasoning}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
