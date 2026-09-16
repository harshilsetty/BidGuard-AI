import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        gov: {
          navy: "#0F2D5B",
          blue: "#1F4E9E",
          accent: "#2E73D6",
          cyan: "#17A2B8",
          bg: "#F5F8FB",
          white: "#FFFFFF",
          border: "#E9EEF5",
          text: "#2B3A55",
          secondary: "#6B7C93",
          success: "#28A745",
          danger: "#DC3545",
          warning: "#FFC107",
        },
        gem: {
          navy: "#0F2D5B",
          dark: "#0a192f",
          card: "#1e293b",
          border: "#334155",
          accent: "#1F4E9E",
          gold: "#FFC107",
        },
      },
    },
  },
  plugins: [],
};
export default config;
