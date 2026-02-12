/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
         black: "hsl(var(--black))",
         secondary: "hsl(var(--secondary))",
        primary: {
          DEFAULT: '#DC7828',
          50: '#fef6ee',
          100: '#fde9d3',
          200: '#fad0a5',
          300: '#f6ae6d',
          400: '#f28433',
          500: '#ef6820',
          600: '#dc7828',
          700: '#b8531a',
          800: '#93421b',
          900: '#77381a',
          950: '#401a0b',
        }
      }
    },
  },
  plugins: [],
}
