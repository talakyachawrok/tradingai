/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      colors: {
        terminal: {
          bg: 'var(--bg-primary)',
          panel: 'var(--bg-panel)',
          elevated: 'var(--bg-elevated)',
          border: 'var(--border-color)',
          text: 'var(--text-primary)',
          muted: 'var(--text-muted)',
        },
      },
    },
  },
  plugins: [],
}
