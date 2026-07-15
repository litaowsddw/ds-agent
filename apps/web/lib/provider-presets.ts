/** Quick-start configuration for common OpenAI-compatible providers. */
export const PROVIDER_PRESETS = [
  {
    key: "openai",
    label: "OpenAI",
    baseUrl: "https://api.openai.com/v1",
    models: "gpt-4o-mini, gpt-4o",
    defaultModel: "gpt-4o-mini",
  },
  {
    key: "deepseek",
    label: "DeepSeek",
    baseUrl: "https://api.deepseek.com/v1",
    models: "deepseek-chat, deepseek-reasoner",
    defaultModel: "deepseek-chat",
  },
  {
    key: "qwen",
    label: "Qwen (DashScope)",
    baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    models: "qwen-turbo, qwen-plus",
    defaultModel: "qwen-plus",
  },
  {
    key: "openrouter",
    label: "OpenRouter",
    baseUrl: "https://openrouter.ai/api/v1",
    models: "openai/gpt-4o-mini, anthropic/claude-3.5-sonnet",
    defaultModel: "openai/gpt-4o-mini",
  },
  {
    key: "siliconflow",
    label: "SiliconFlow",
    baseUrl: "https://api.siliconflow.cn/v1",
    models: "deepseek-ai/DeepSeek-V3, Qwen/Qwen2.5-7B-Instruct",
    defaultModel: "deepseek-ai/DeepSeek-V3",
  },
  {
    key: "ollama",
    label: "Ollama (Local)",
    baseUrl: "http://127.0.0.1:11434/v1",
    models: "deepseek-r1:1.5b",
    defaultModel: "deepseek-r1:1.5b",
  },
] as const;
