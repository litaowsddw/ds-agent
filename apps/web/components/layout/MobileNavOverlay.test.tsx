import { fireEvent, render, screen } from "@testing-library/react";
import type { AnchorHTMLAttributes } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Header from "@/components/layout/Header";
import AppLayout from "@/components/layout/AppLayout";
import MobileNavOverlay from "@/components/layout/MobileNavOverlay";
import { useWorkspaceStore } from "@/stores/workspace";

const routing = vi.hoisted(() => ({ pathname: "/agents" }));

vi.mock("next/navigation", () => ({
  usePathname: () => routing.pathname,
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("@/lib/api", () => ({
  checkHealth: vi.fn().mockResolvedValue({ status: "ok" }),
}));

vi.mock("next/link", () => ({
  default: ({ children, onClick, ...props }: AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a
      {...props}
      onClick={(event) => {
        event.preventDefault();
        onClick?.(event);
      }}
    >
      {children}
    </a>
  ),
}));

describe("MobileNavOverlay", () => {
  beforeEach(() => {
    routing.pathname = "/agents";
    useWorkspaceStore.setState({
      workspace: null,
      agents: [],
      selectedAgentId: "",
      busy: false,
      apiStatus: "online",
    });
  });

  it("is hidden from assistive technology while closed", () => {
    render(<MobileNavOverlay open={false} onClose={vi.fn()} />);

    expect(screen.getByTestId("mobile-navigation-overlay")).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByRole("link", { name: "Home", hidden: true })).toHaveAttribute("tabindex", "-1");
  });

  it("moves focus into the drawer and traps focus while open", () => {
    render(<MobileNavOverlay open onClose={vi.fn()} />);
    const firstLink = screen.getAllByRole("link")[0];
    const lastLink = screen.getByRole("link", { name: "Chat" });

    expect(firstLink).toHaveFocus();

    lastLink.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(firstLink).toHaveFocus();

    firstLink.focus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(lastLink).toHaveFocus();
  });

  it("locks body scroll and returns focus when closed", () => {
    const trigger = document.createElement("button");
    document.body.appendChild(trigger);
    trigger.focus();
    const { rerender } = render(<MobileNavOverlay open onClose={vi.fn()} />);

    expect(document.body.style.overflow).toBe("hidden");

    rerender(<MobileNavOverlay open={false} onClose={vi.fn()} />);

    expect(document.body.style.overflow).toBe("");
    expect(trigger).toHaveFocus();
    trigger.remove();
  });

  it("dismisses on Escape", () => {
    const onClose = vi.fn();
    render(<MobileNavOverlay open onClose={onClose} />);

    fireEvent.keyDown(document, { key: "Escape" });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("dismisses when the backdrop is clicked", () => {
    const onClose = vi.fn();
    render(<MobileNavOverlay open onClose={onClose} />);

    fireEvent.click(screen.getByRole("button", { name: /close navigation/i }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("dismisses after navigation", () => {
    const onClose = vi.fn();
    render(<MobileNavOverlay open onClose={onClose} />);

    fireEvent.click(screen.getByRole("link", { name: "Workflow" }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("AppLayout mobile navigation", () => {
  it("closes navigation when pathname changes", () => {
    const { rerender } = render(<AppLayout><div>Content</div></AppLayout>);
    fireEvent.click(screen.getByRole("button", { name: /open navigation/i }));
    expect(screen.getByTestId("mobile-navigation-overlay")).toHaveAttribute("aria-hidden", "false");

    routing.pathname = "/runs";
    rerender(<AppLayout><div>Content</div></AppLayout>);

    expect(screen.getByTestId("mobile-navigation-overlay")).toHaveAttribute("aria-hidden", "true");
  });
});

describe("Header mobile navigation trigger", () => {
  it("reports expanded state and opens navigation", () => {
    const onOpenNavigation = vi.fn();
    render(<Header navigationOpen={false} onOpenNavigation={onOpenNavigation} />);
    const trigger = screen.getByRole("button", { name: /open navigation/i });

    expect(trigger).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(trigger);

    expect(onOpenNavigation).toHaveBeenCalledTimes(1);
  });
});
