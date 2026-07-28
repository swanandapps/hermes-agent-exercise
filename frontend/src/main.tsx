import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

// Fonts are vendored rather than pulled from a CDN — the demo must not depend on
// external network at run time.
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-mono/600.css";
import "@fontsource/newsreader/400.css";
import "@fontsource/newsreader/500.css";

import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
