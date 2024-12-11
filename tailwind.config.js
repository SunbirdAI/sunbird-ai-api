/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/templates/**/*.html"],
  theme: {
    extend: {
      colors: {
        orange: { 500: "#ffAA28" },
      },
    },
  },
  plugins: [],
};
