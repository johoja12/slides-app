/* Public position bridge. Never carries notes, credentials or deck content. */
(() => {
  "use strict";
  let connected = false;
  function connect() {
    const api = window.slidesPlayerController;
    if (!api || connected) return;
    connected = true;
    function report() {
      const s = api.getState();
      if (s)
        parent.postMessage(
          { type: "slides-position", index: s.index, count: s.count },
          location.origin,
        );
    }
    addEventListener("message", (event) => {
      if (event.origin !== location.origin || event.source !== parent) return;
      const value = event.data;
      if (
        value?.type === "slides-navigate" &&
        Number.isInteger(value.index) &&
        value.index >= 0 &&
        value.index < 10000
      )
        api.go(value.index);
      if (value?.type === "slides-request-position") report();
    });
    addEventListener("slides-position-change", report);
    setInterval(report, 2000);
    report();
  }
  addEventListener("slides-player-ready", connect);
  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", connect, { once: true });
  else connect();
})();
