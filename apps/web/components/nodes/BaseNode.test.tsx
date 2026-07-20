import { describe, expect, it } from "vitest";
import { getNodeDisplay, type BaseNodeData } from "@/components/nodes/BaseNode";

describe("getNodeDisplay", () => {
  const defaults: BaseNodeData = {
    label: "LLM",
    description: "Model call",
    capability: "executable",
  };

  it("keeps the type defaults until an author gives the node a visual identity", () => {
    expect(getNodeDisplay(defaults)).toEqual({ label: "LLM", description: "Model call" });
  });

  it("uses saved display metadata and ignores whitespace-only overrides", () => {
    expect(
      getNodeDisplay({
        ...defaults,
        config: { display_name: "  Answer with cited sources  ", display_description: "  Final response step  " },
      })
    ).toEqual({ label: "Answer with cited sources", description: "Final response step" });

    expect(getNodeDisplay({ ...defaults, config: { display_name: "  ", display_description: "" } })).toEqual({
      label: "LLM",
      description: "Model call",
    });
  });
});
