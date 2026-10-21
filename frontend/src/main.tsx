import React from "react";
import ReactDOM from "react-dom/client";
import { Provider } from "react-redux";
import { store } from "./store";
import App from "./App";
import "./index.css";
import { isNative } from "./platform";

// Inside the installed app, pinch zooms the screen (zoomEnabled in
// capacitor.config.ts) and a double-tap does nothing: it zoomed in or out
// unpredictably, and a pinch is the gesture people expect to control.
if (isNative()) {
  document.documentElement.classList.add("native-app");
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Provider store={store}>
      <App />
    </Provider>
  </React.StrictMode>
);
