import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import AgentReadinessNotice from "@/components/agents/AgentReadinessNotice";

describe("AgentReadinessNotice", () => {
  it("directs a first-time user to configure a model before creating an Agent", () => {
    render(<AgentReadinessNotice modelProviderCount={0} />);

    expect(screen.getByText("先配置模型，再创建可对话的 Agent")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /配置模型供应商/ })).toHaveAttribute("href", "/models");
  });

  it("explains why an existing Agent without a model cannot chat", () => {
    render(
      <AgentReadinessNotice
        modelProviderCount={1}
        agent={{ name: "研究助手", model_provider: "", model_name: "" }}
      />
    );

    expect(screen.getByText("为「研究助手」绑定默认模型")).toBeInTheDocument();
    expect(screen.getByText(/尚不能直接对话/)).toBeInTheDocument();
  });

  it("offers an immediate chat action after creating a ready Agent", () => {
    render(<AgentReadinessNotice modelProviderCount={1} createdAgentName="研究助手" />);

    expect(screen.getByText("「研究助手」已可开始对话")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /开始对话/ })).toHaveAttribute("href", "/chat");
  });

  it("stays out of the way for a chat-ready Agent", () => {
    const { container } = render(
      <AgentReadinessNotice
        modelProviderCount={1}
        agent={{ name: "研究助手", model_provider: "deepseek", model_name: "deepseek-chat" }}
      />
    );

    expect(container).toBeEmptyDOMElement();
  });
});
