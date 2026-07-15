import { beforeEach, describe, expect, it, vi } from "vitest";

const { apiRequestMock } = vi.hoisted(() => ({ apiRequestMock: vi.fn() }));

vi.mock("@/lib/api", () => ({ apiRequest: apiRequestMock }));

import { useRuntimeStore } from "@/stores/runtime";

describe("external capability imports", () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
    useRuntimeStore.setState({
      skills: [],
      mcpServers: [],
      mcpTools: [],
      mcpImportForm: { name: "", url: "", bearerToken: "", apiKey: "" },
      skillImportUrl: "",
    });
  });

  it("discovers and binds an external MCP service without a hand-authored tool", async () => {
    useRuntimeStore.setState({
      mcpImportForm: {
        name: "GitHub MCP",
        url: "https://mcp.example.test/mcp",
        bearerToken: "secret-token",
        apiKey: "",
      },
    });
    apiRequestMock.mockResolvedValueOnce({
      agent_id: "agent-1",
      server: { server_id: "mcp-1", name: "GitHub MCP", transport: "streamable_http", url: "https://mcp.example.test/mcp" },
      tools: [{ tool_id: "tool-1", name: "search", description: "Search", risk_level: "low" }],
    });

    await useRuntimeStore.getState().importMcpServer("user-1", "agent-1");

    expect(apiRequestMock).toHaveBeenCalledWith("/mcp/agents/agent-1/import", {
      method: "POST",
      body: {
        actor_user_id: "user-1",
        name: "GitHub MCP",
        transport: "streamable_http",
        url: "https://mcp.example.test/mcp",
        credentials: { bearer_token: "secret-token" },
      },
    });
    expect(useRuntimeStore.getState().mcpTools).toHaveLength(1);
    expect(useRuntimeStore.getState().mcpImportForm).toEqual({ name: "", url: "", bearerToken: "", apiKey: "" });
  });

  it("imports one GitHub SKILL.md and binds it to the selected agent", async () => {
    useRuntimeStore.setState({ skillImportUrl: "https://github.com/openai/skills/blob/main/SKILL.md" });
    apiRequestMock.mockResolvedValueOnce({
      skill_id: "skill-1",
      name: "example-skill",
      description: "Example",
      scope: "agent",
    });

    await useRuntimeStore.getState().importGithubSkill("user-1", "org-1", "agent-1");

    expect(apiRequestMock).toHaveBeenCalledWith("/skills/import", {
      method: "POST",
      body: {
        actor_user_id: "user-1",
        org_id: "org-1",
        agent_id: "agent-1",
        source_url: "https://github.com/openai/skills/blob/main/SKILL.md",
      },
    });
    expect(useRuntimeStore.getState().skills).toHaveLength(1);
    expect(useRuntimeStore.getState().skillImportUrl).toBe("");
  });
});
