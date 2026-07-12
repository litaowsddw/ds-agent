import { fireEvent, render, screen } from "@testing-library/react";
import type { AnchorHTMLAttributes } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Header from "@/components/layout/Header";
import MobileNavOverlay from "@/components/layout/MobileNavOverlay";
import { useWorkspaceStore } from "@/stores/workspace";

vi.mock("next/navigation", () => ({
  usePathname: () => "/agents",
  useRouter: () => ({ push: vi.fn() }),
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
