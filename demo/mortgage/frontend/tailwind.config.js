/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bank: {
          dark: '#1a1a2e',
          primary: '#16213e',
          accent: '#0f3460',
          highlight: '#e94560',
          teal: '#14B8A6',
          gold: '#f0c040',
          light: '#f4f4f8',
        },
      },
    },
  },
  plugins: [],
}
