/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        primary: "#2563EB",
        primaryHover: "#1D4ED8",
        primarySoft: "#3B82F6",
        ink: "#0B1220",
        bgLight: "#F8FAFC",
        bgBlueTint: "#EFF6FF",
      },
      fontFamily: {
        sans: ["Inter", "sans-serif"],
      },
      borderRadius: {
        card: "12px",
        btn: "8px",
      },
      boxShadow: {
        card: "0 1px 2px 0 rgba(15,23,42,0.04), 0 1px 3px 0 rgba(15,23,42,0.06)",
        "card-lg":
          "0 12px 32px -8px rgba(15,23,42,0.16), 0 4px 10px -4px rgba(15,23,42,0.08)",
        "panel-glow": "0 0 120px 40px rgba(37,99,235,0.25)",
      },
    },
  },
  plugins: [],
};
