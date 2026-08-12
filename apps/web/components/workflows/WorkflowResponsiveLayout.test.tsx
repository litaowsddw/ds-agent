import { fireEvent, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import WorkflowResponsiveLayout from "@/components/workflows/WorkflowResponsiveLayout";

describe("WorkflowResponsiveLayout", () => {
  it("exposes controlled mobile drawers with ARIA state", () => {
    renderLayout();
    const nodesTrigger = screen.getByRole("button", { name: "Nodes" });
    const inspectorTrigger = screen.getByRole("button", { name: "Workflow & inspector" });

    expect(nodesTrigger).toHaveAttribute("aria-expanded", "false");
    expect(nodesTrigger).toHaveAttribute("aria-controls", "workflow-mobile-palette");
    expect(inspectorTrigger).toHaveAttribute("aria-expanded", "false");
    expect(inspectorTrigger).toHaveAttribute("aria-controls", "workflow-mobile-inspector");

    fireEvent.click(nodesTrigger);

    expect(nodesTrigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("dialog", { name: "Nodes" })).toHaveAttribute("id", "workflow-mobile-palette");
    expect(screen.getByTestId("workflow-responsive-background")).toHaveAttribute("inert");
  });

  it("focuses the drawer, closes on Escape, and returns focus", () => {
    renderLayout();
    const trigger = screen.getByRole("button", { name: "Workflow & inspector" });
    trigger.focus();
    fireEvent.click(trigger);

    expect(screen.getByRole("button", { name: "Close Workflow & inspector" })).toHaveFocus();
    fireEvent.keyDown(document, { key: "Escape" });

    expect(screen.queryByRole("dialog", { name: "Workflow & inspector" })).not.toBeInTheDocument();
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(trigger).toHaveFocus();
  });

  it("closes from the backdrop", () => {
    renderLayout();
    fireEvent.click(screen.getByRole("button", { name: "Nodes" }));

    fireEvent.click(screen.getByRole("button", { name: "Close workflow drawer" }));

    expect(screen.queryByRole("dialog", { name: "Nodes" })).not.toBeInTheDocument();
  });
});

describe("Workflow canvas sizing", () => {
  it("uses flex sizing instead of a fixed header-height calculation", () => {
    const pageSource = readFileSync(resolve(process.cwd(), "app/workflows/page.tsx"), "utf8");
    const canvasSource = readFileSync(
      resolve(process.cwd(), "components/workflows/editor/WorkflowEditorCanvas.tsx"),
      "utf8"
    );

    expect(pageSource).not.toContain("h-[calc(100%-58px)]");
    expect(canvasSource).not.toContain("h-[calc(100%-58px)]");
    expect(canvasSource).toContain('className="relative min-h-0 flex-1 bg-[#f7f8fa]"');
  });
});

function renderLayout() {
  return render(
    <WorkflowResponsiveLayout
      canvas={<div>Canvas</div>}
      inspector={<button type="button">Inspector action</button>}
      palette={<button type="button">Palette action</button>}
    />
  );
}
