import { describe, expect, it } from "vitest";
import { PROVIDER_PRESETS } from "@/lib/provider-presets";

describe("PROVIDER_PRESETS", () => {
  it("offers the supported OpenAI-compatible provider quick-starts", () => {
    expect(PROVIDER_PRESETS.map((preset) => preset.key)).toEqual([
      "openai",
      "deepseek",
      "qwen",
      "openrouter",
      "siliconflow",
      "ollama",
    ]);

    for (const preset of PROVIDER_PRESETS) {
      expect(preset.baseUrl).toMatch(/^https?:\/\//);
      expect(preset.models).not.toBe("");
      expect(preset.defaultModel).not.toBe("");
    }
  });
});
