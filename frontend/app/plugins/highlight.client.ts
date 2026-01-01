// Import highlight.js styles
import "highlight.js/styles/atom-one-dark.css";

export default defineNuxtPlugin(() => {
  // Client initialization logic
  if (process.client) {
    // Add custom styles to ensure transparent background for the code block
    // so it uses our container background
    const style = document.createElement("style");
    style.textContent = `
      .hljs {
        background: transparent !important;
      }
    `;
    document.head.appendChild(style);
  }
});
