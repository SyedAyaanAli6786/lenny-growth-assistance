/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#effcf6",
          100: "#d7f7ea",
          200: "#b2eed8",
          300: "#7ddfbe",
          400: "#45c99f",
          500: "#20ab83",
          600: "#14896a",
          700: "#136d57",
          800: "#125747",
          900: "#10483c",
        },
      },
      keyframes: {
        "bounce-dot": {
          "0%, 80%, 100%": { transform: "scale(0.6)", opacity: "0.4" },
          "40%": { transform: "scale(1)", opacity: "1" },
        },
        "fade-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "bounce-dot": "bounce-dot 1.2s infinite ease-in-out both",
        "fade-in": "fade-in 0.15s ease-out",
      },
    },
  },
  plugins: [
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    require("@tailwindcss/typography"),
  ],
};
