import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const { getUsageEventsMock } = vi.hoisted(() => ({
  getUsageEventsMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams("agent=agent-1"),
}));

vi.mock("@/lib/api", () => ({
  getUsageEvents: getUsageEventsMock,
}));

import InsightsPage from "@/app/insights/page";

describe("InsightsPage", () => {
  it("labels unknown provider usage as unavailable instead of zero", async () => {
    getUsageEventsMock.mockResolvedValue({
      org_id: "org-1",
      created_at_from: "2026-07-07T00:00:00Z",
      created_at_to: "2026-07-14T00:00:00Z",
      events: [{
        event_id: "event-1",
        gateway_call_id: "call-1",
        created_at: "2026-07-14T00:00:00Z",
        source: "workflow_node",
        api_name: "chat.completions",
        provider_key: "openai",
        model: "gpt-4o",
        dispatch_status: "succeeded",
        usage_status: "unavailable",
        cache_usage_status: "unknown",
        input_tokens: null,
        output_tokens: null,
        total_tokens: null,
        cache_read_input_tokens: null,
      }],
      offset: 0,
      limit: 200,
    });

    render(<InsightsPage />);

    expect((await screen.findAllByText("Provider 未提供用量")).length).toBeGreaterThan(0);
    expect(screen.queryByText("0 Token")).not.toBeInTheDocument();
    expect(getUsageEventsMock).toHaveBeenCalledWith(
      expect.objectContaining({ agent_id: "agent-1" })
    );
  });

  it("does not show incomplete aggregates when event pagination reaches its limit", async () => {
    getUsageEventsMock.mockResolvedValue({
      org_id: "org-1", created_at_from: "2026-07-07T00:00:00Z", created_at_to: "2026-07-14T00:00:00Z",
      events: Array.from({ length: 200 }, (_, index) => ({
        event_id: `event-${index}`, gateway_call_id: `call-${index}`, created_at: "2026-07-14T00:00:00Z",
        source: "workflow_node", api_name: "chat.completions", provider_key: "openai", model: "gpt-4o",
        dispatch_status: "succeeded", usage_status: "provider_final", cache_usage_status: "known",
      })), offset: 0, limit: 200, has_more: true,
    });

    render(<InsightsPage />);

    expect(await screen.findByText(/无法保证汇总完整/)).toBeInTheDocument();
    expect(screen.queryByText("按模型汇总")).not.toBeInTheDocument();
  });
});
