/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#F6F7F9",
        card: "#FFFFFF",
        ink: "#12172B",
        primary: "#1D2A54",
        verified: "#146C43",
        unverified: "#A15C07",
        destructive: "#B91C1C",
        hairline: "#DADFE7",
        muted: "#5B6472",
      },
      fontFamily: {
        serif: ["Newsreader", "Georgia", "serif"],
        sans: ["IBM Plex Sans", "sans-serif"],
        mono: ["IBM Plex Mono", "monospace"],
      },
    },
  },
  plugins: [],
};
