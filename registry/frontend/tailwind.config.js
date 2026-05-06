/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Recursant brand palette — dark navy + teal mesh aesthetic.
        brand: {
          dark: '#0C1117',         // page background (matches the logo's bg)
          darker: '#070B15',
          bg: '#0D1424',           // app background (one step lighter than dark)
          surface: '#111A2E',      // cards, panels
          'surface-hi': '#162038', // raised surfaces, modal headers
          border: '#243155',       // subtle borders / dividers
          'border-hi': '#2F4170',  // emphasised borders
          teal: '#14B8A6',
          'teal-deep': '#0F9690',
          'teal-soft': '#1DD3BD',
          green: '#06D6A0',
          text: '#E8F4F2',         // primary text
          muted: '#A6B6C9',        // secondary text
          dim: '#6B7A93',          // tertiary text / placeholders
          light: '#E8F4F2',        // legacy alias
        },
      },
    },
    // Override stock light-theme colors so the existing 30+ pages
    // (which use `bg-white`, `text-gray-900`, `border-gray-200`, etc.)
    // automatically pick up the dark theme without per-page edits.
    // Keep the names so future Tailwind utilities still work.
    colors: {
      transparent: 'transparent',
      current: 'currentColor',
      black: '#000000',
      white: '#111A2E',         // map "white" -> brand surface (dark card)
      gray: {
        50:  '#0D1424',
        100: '#111A2E',
        200: '#243155',
        300: '#2F4170',
        400: '#6B7A93',
        500: '#A6B6C9',         // muted secondary text
        600: '#B8C5D7',
        700: '#D2DCEB',         // body text on dark
        800: '#E0E8F4',
        900: '#E8F4F2',         // primary text
      },
      // Status colours — kept vivid but tuned for dark backgrounds.
      red: {
        50:  '#3A1116',
        100: '#4A1620',
        200: '#5A1B2A',
        300: '#7A2535',
        400: '#FF6B7A',
        500: '#F87171',
        600: '#EF4444',
        700: '#FCA5A5',
        800: '#FECACA',
        900: '#FECACA',
      },
      green: {
        50:  '#0F2B1F',
        100: '#143D2A',
        200: '#1A5036',
        300: '#246C4B',
        400: '#34D399',
        500: '#10B981',
        600: '#059669',
        700: '#A7F3D0',
        800: '#D1FAE5',
        900: '#D1FAE5',
      },
      yellow: {
        50:  '#3A2D0E',
        100: '#4A3A12',
        200: '#5C481A',
        300: '#7A5F22',
        400: '#FBBF24',
        500: '#F59E0B',
        600: '#D97706',
        700: '#FDE68A',
        800: '#FEF3C7',
        900: '#FEF3C7',
      },
      blue: {
        50:  '#0F1E3A',
        100: '#142654',
        200: '#1E3168',
        300: '#274285',
        400: '#60A5FA',
        500: '#3B82F6',
        600: '#2563EB',
        700: '#93C5FD',
        800: '#BFDBFE',
        900: '#BFDBFE',
      },
      teal: {
        50:  '#0E2D2A',
        100: '#0F9690',
        200: '#14A89B',
        300: '#14B8A6',
        400: '#1DD3BD',
        500: '#14B8A6',
        600: '#0F9690',
        700: '#A7F3E8',
        800: '#CCFBF1',
        900: '#E8F4F2',
      },
      // amber/indigo/orange/etc. fall back to tealless dark surfaces if used.
      amber: { 50: '#3A2D0E', 100: '#4A3A12', 500: '#F59E0B', 700: '#FDE68A', 900: '#FEF3C7' },
      indigo: { 50: '#1A1F3A', 100: '#252B4A', 500: '#818CF8', 700: '#C7D2FE', 900: '#E0E7FF' },
      orange: { 50: '#3A1F0E', 100: '#4A2812', 500: '#FB923C', 700: '#FDBA74', 900: '#FED7AA' },
      pink: { 50: '#3A0F26', 100: '#4A1230', 500: '#F472B6', 700: '#F9A8D4', 900: '#FBCFE8' },
      purple: { 50: '#1F0F3A', 100: '#28124A', 500: '#A78BFA', 700: '#C4B5FD', 900: '#E9D5FF' },
    },
  },
  plugins: [],
}
