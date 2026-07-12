import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import AgentContextSelect from "@/components/layout/AgentContextSelect";
import { useWorkspaceStore } from "@/stores/workspace";
import type { Agent } from "@/types/agent";

const firstAgent = agent("agent-1", "Research Agent");
const secondAgent = agent("agent-2", "Writing Agent");

describe("AgentContextSelect", () => {
  beforeEach(() => {
    useWorkspaceStore.setState({
      workspace: null,
      agents: [],
      selectedAgentId: "",
      busy: false,
    });
  });

  it("links to Agents when no agents exist", () => {
    render(<AgentContextSelect />);

    expect(screen.getByRole("link", { name: "创建 Agent" })).toHaveAttribute("href", "/agents");
  });

  it("shows the current global agent selection", () => {
    useWorkspaceStore.setState({
      agents: [firstAgent, secondAgent],
      selectedAgentId: secondAgent.agent_id,
    });

    render(<AgentContextSelect />);

    expect(screen.getByRole("combobox", { name: /agent context/i })).toHaveValue(secondAgent.agent_id);
    expect(screen.getByRole("option", { name: "选择 Agent" })).toBeInTheDocument();
  });

  it("updates the global agent selection on change", () => {
    useWorkspaceStore.setState({
      agents: [firstAgent, secondAgent],
      selectedAgentId: firstAgent.agent_id,
    });
    render(<AgentContextSelect />);

    fireEvent.change(screen.getByRole("combobox", { name: /agent context/i }), {
      target: { value: secondAgent.agent_id },
    });

    expect(useWorkspaceStore.getState().selectedAgentId).toBe(secondAgent.agent_id);
  });

  it("disables selection while the workspace is busy", () => {
    useWorkspaceStore.setState({
      agents: [firstAgent, secondAgent],
      selectedAgentId: firstAgent.agent_id,
      busy: true,
    });

    render(<AgentContextSelect />);

    expect(screen.getByRole("combobox", { name: /agent context/i })).toBeDisabled();
  });

  it("cleans stale selections and auto-selects a sole agent", () => {
    useWorkspaceStore.setState({
      agents: [firstAgent],
      selectedAgentId: firstAgent.agent_id,
    });

    useWorkspaceStore.getState().setAgents([secondAgent, agent("agent-3", "Review Agent")]);
    expect(useWorkspaceStore.getState().selectedAgentId).toBe("");

    useWorkspaceStore.getState().setAgents([secondAgent]);
    expect(useWorkspaceStore.getState().selectedAgentId).toBe(secondAgent.agent_id);
  });
});

function agent(agentId: string, name: string): Agent {
  return {
    agent_id: agentId,
    org_id: "org-1",
    team_id: "team-1",
    name,
    description: "",
    created_by: "user-1",
  };
}
