// postcss.config.js
// PostCSS is a tool that transforms your CSS using JavaScript plugins.
// Think of it like Babel (which transforms JS), but for CSS.
//
// The two plugins we use:
//
// 1. tailwindcss — reads your JSX/TSX files, finds every Tailwind class
//    you used (like "bg-gray-900", "flex", "p-4"), and generates the
//    actual CSS rules for just those classes. This is what makes Tailwind work.
//
// 2. autoprefixer — automatically adds browser-specific CSS prefixes
//    like -webkit-, -moz- so your styles work across all browsers.
//    You write: display: flex;
//    It outputs: display: -webkit-flex; display: -ms-flexbox; display: flex;
//    You never have to think about cross-browser compatibility.

module.exports = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
