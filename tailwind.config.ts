// tailwind.config.ts
// Tailwind CSS is a "utility-first" CSS framework.
// Instead of writing a separate .css file with classes like:
//   .button { background: blue; padding: 8px; border-radius: 4px; }
// ...you write utility classes directly in your JSX:
//   <button className="bg-blue-500 p-2 rounded">Click me</button>
//
// This config tells Tailwind:
//   1. WHERE to look for class names (the `content` array)
//   2. Any custom design tokens you want to add beyond Tailwind's defaults

import type { Config } from "tailwindcss";

const config: Config = {
  // Tailwind scans these file patterns for class names so it can
  // include ONLY the CSS you actually use — called "purging" or "tree-shaking".
  // Without this, Tailwind would ship ~3MB of CSS. With it: usually <10KB.
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      // Custom animation for the typing indicator dots
      // (the three bouncing dots shown while AI is generating a response)
      keyframes: {
        dotBounce: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-5px)" },
        },
      },
      animation: {
        "dot-bounce": "dotBounce 0.8s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
