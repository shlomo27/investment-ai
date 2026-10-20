import React from "react";
import ReactDOM from "react-dom/client";
import { Provider } from "react-redux";
import { store } from "./store";
import App from "./App";
import "./index.css";
import { isNative } from "./platform";

// Inside the installed app the screen behaves like a native one: it fits the
// phone and does not zoom. Page zoom was left on from the website, so a
// double-tap zoomed in or out unpredictably, a pinch did nothing useful, and
// a zoomed page hid half the data with no clear way back. The charts keep
// their own pinch-to-zoom. The website stays zoomable for accessibility.
if (isNative()) {
  document
    .querySelector('meta[name="viewport"]')
    ?.setAttribute(
      "content",
      "width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover",
    );
  document.documentElement.classList.add("native-app");
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Provider store={store}>
      <App />
    </Provider>
  </React.StrictMode>
);
