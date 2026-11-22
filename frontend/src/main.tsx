import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import { listenForInstallPrompt } from "./lib/install";
import "./index.css";

listenForInstallPrompt();

// The service worker keeps the app itself on the phone so it opens offline. Production only:
// in development it would serve stale code.
if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      /* the app works without it */
    });
  });
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
