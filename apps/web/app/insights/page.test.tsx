import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const { getUsageSummaryMock, getUsageEventsMock } = vi.hoisted(() => ({
  getUsageSummaryMock: vi.fn(),
  getUsageEventsMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams("agent=agent-1"),
}));

vi.mock("@/lib/api", () => ({
  getUsageSummary: getUsageSummaryMock,
  getUsageEvents: getUsageEventsMock,
}));

import InsightsPage from "@/app/insights/page";

describe("InsightsPage", () => {
  it("labels unknown provider usage as unavailable instead of zero", async () => {
    getUsageSummaryMock.mockResolvedValue({
      org_id: "org-1",
      group_by: "model",
      granularity: "day",
      created_at_from: "2026-07-07T00:00:00Z",
      created_at_to: "2026-07-14T00:00:00Z",
      groups: [
        {
          model: "gpt-4o",
          call_count: 1,
          unknown_usage_calls: 1,
          input_tokens: null,
          output_tokens: null,
          total_tokens: null,
          cache_read_input_tokens: null,
        },
      ],
    });
    getUsageEventsMock.mockResolvedValue({
      org_id: "org-1",
      created_at_from: "2026-07-07T00:00:00Z",
      created_at_to: "2026-07-14T00:00:00Z",
      events: [],
      offset: 0,
      limit: 200,
    });

    render(<InsightsPage />);

    expect((await screen.findAllByText("Provider 未提供用量")).length).toBeGreaterThan(0);
    expect(screen.queryByText("0 Token")).not.toBeInTheDocument();
    expect(getUsageSummaryMock).toHaveBeenCalledWith(
      expect.objectContaining({ agent_id: "agent-1" })
    );
  });
});
