import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./features/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#f7f8fa",
        panel: "#ffffff",
        ink: "#18202f",
        muted: "#647084",
        line: "#d9dee8",
        accent: "#1677ff",
        success: "#15803d",
        warning: "#b45309"
      }
    }
  },
  plugins: []
};

export default config;

