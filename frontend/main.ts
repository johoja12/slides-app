import "vite/modulepreload-polyfill";
import { createApp } from "vue";
import type { Component } from "vue";
import type { Bootstrap, Page } from "./types";
import { csrfKey } from "./composables/api";
import LibraryPage from "./pages/LibraryPage.vue";
import UploadPage from "./pages/UploadPage.vue";
import HistoryPage from "./pages/HistoryPage.vue";
import SearchPage from "./pages/SearchPage.vue";
import SharesPage from "./pages/SharesPage.vue";
import ViewerPage from "./pages/ViewerPage.vue";
import PresenterPage from "./pages/PresenterPage.vue";
import "./style.css";
const pages: Record<Page, Component> = {
  library: LibraryPage,
  upload: UploadPage,
  history: HistoryPage,
  search: SearchPage,
  shares: SharesPage,
  viewer: ViewerPage,
  presenter: PresenterPage,
};
const root = document.querySelector<HTMLElement>("#app");
const element = document.querySelector<HTMLScriptElement>("#ui-bootstrap");
if (root && element) {
  try {
    const bootstrap = JSON.parse(element.textContent || "") as Bootstrap;
    if (
      !Object.hasOwn(pages, bootstrap.page) ||
      typeof bootstrap.csrf !== "string" ||
      !bootstrap.data ||
      typeof bootstrap.data !== "object"
    )
      throw new Error("Invalid bootstrap");
    const app = createApp(pages[bootstrap.page], { data: bootstrap.data });
    app.provide(csrfKey, bootstrap.csrf);
    app.mount(root);
    root.dataset.mounted = "vue";
    element.remove(); // Minimize duplicate private state in the live document.
  } catch {
    const status = root.querySelector('[role="status"]');
    if (status)
      status.textContent =
        "The application could not load. Refresh the page and try again.";
  }
}
