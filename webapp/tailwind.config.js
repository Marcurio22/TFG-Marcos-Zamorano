/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./trazasytrazadas/templates/**/*.html",
    "./trazasytrazadas/static/**/*.js"
  ],
  plugins: [require("daisyui")],
};