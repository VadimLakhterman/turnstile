/** Tailwind build for landing/index.html. Rebuild after changing classes in the page:
 *  npx --yes tailwindcss@3.4.17 -c landing-build/tailwind.config.js -i landing-build/input.css -o landing/tailwind.css --minify
 */
module.exports = {
  content: ["./landing/index.html"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
};
