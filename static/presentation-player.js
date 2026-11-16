/* Public, app-owned player. Decks supply content and navigation hooks, never chrome. */
(() => {
  "use strict";
  const options = { ...document.currentScript?.dataset };
  function start() {
    if (document.querySelector("slides-player")) return;
    const nativeControls = (selector) => document.querySelector(selector);
    const click = (selector) => nativeControls(selector)?.click();
    const canonical = window.slidesDeck;
    const policy = window.policyDeck;
    const canvas =
      typeof slides !== "undefined" &&
      Array.isArray(slides) &&
      typeof idx !== "undefined" &&
      typeof go === "function";
    const sections = [...document.querySelectorAll("[data-slide]")];
    let sectionIndex = 0;
    let adapter;
    if (
      canonical &&
      canonical.version === 1 &&
      typeof canonical.getState === "function" &&
      typeof canonical.go === "function"
    ) {
      adapter = canonical;
    } else if (
      policy &&
      typeof policy.getState === "function" &&
      typeof policy.go === "function"
    ) {
      adapter = {
        getState: () => {
          const s = policy.getState();
          return {
            index: s.slide,
            count: s.total,
            step: s.build,
            steps: s.builds + 1,
            playing: s.playing,
          };
        },
        go: (n) => policy.go(n),
        next: () => policy.next(),
        previous: () => policy.prev(),
        titles: policy.titles,
        thumbnails: policy.titles.map(
          (_, i) => `assets/slide-thumbnails/slide-${i + 1}.png`,
        ),
        pause: () => {
          if (typeof pause === "function") pause();
          if (typeof stopMotion === "function") stopMotion();
        },
        play: () => click("#play"),
        replay: () => click("#replay"),
        sources: () => click("[data-notes]"),
        resize: (box) => {
          const stage = document.querySelector("#slide");
          if (!stage) return;
          stage.style.top = `${box.top + box.height / 2}px`;
          stage.style.transform = `translate(-50%,-50%) scale(${Math.min(box.width / 1600, box.height / 900)})`;
        },
      };
    } else if (canvas) {
      adapter = {
        getState: () => ({
          index: idx,
          count: slides.length,
          playing: typeof paused === "boolean" ? !paused : false,
        }),
        go: (n) => go(n),
        next: () => go(idx + 1),
        previous: () => go(idx - 1),
        titles: slides.map((s, i) => s.h || `Slide ${i + 1}`),
        thumbnails:
          options.thumbnails === "yes"
            ? slides.map(
                (_, i) =>
                  `navigation/thumbnails/slide-${String(i + 1).padStart(2, "0")}.png?v=${encodeURIComponent(options.version || "")}`,
              )
            : [],
        ...(nativeControls(".ui #pause")
          ? { play: () => click(".ui #pause") }
          : {}),
        pause: () => {
          if (typeof paused === "boolean" && !paused) click(".ui #pause");
        },
        replay: () =>
          nativeControls(".ui #replay") ? click(".ui #replay") : go(idx),
        resize: (box) => {
          const stage = document.querySelector("#stage"),
            viewport = document.querySelector("#viewport");
          if (!stage || !viewport) return;
          viewport.style.left = "0";
          viewport.style.top = `${box.top}px`;
          viewport.style.bottom = `${box.bottom}px`;
          const scale = Math.min(box.width / 1600, box.height / 900) * 0.96;
          stage.style.transform = `translate(-50%,-50%) scale(${scale})`;
          if (
            typeof cv !== "undefined" &&
            typeof ctx !== "undefined" &&
            typeof CW !== "undefined" &&
            typeof CH !== "undefined"
          ) {
            const dpr =
              Math.min(devicePixelRatio || 1, 2) * Math.max(scale, 0.5);
            cv.width = Math.round(CW * dpr);
            cv.height = Math.round(CH * dpr);
            ctx.setTransform(cv.width / CW, 0, 0, cv.height / CH, 0, 0);
          }
        },
      };
    } else {
      adapter = {
        getState: () => ({ index: sectionIndex, count: sections.length || 1 }),
        go: (n) => {
          sectionIndex = n;
          sections.forEach((s, i) => {
            s.hidden = i !== n;
          });
          if (sections.length) history.replaceState(null, "", `#${n + 1}`);
        },
        titles: sections.map(
          (s, i) =>
            s.dataset.title ||
            s.querySelector("h1,h2")?.textContent ||
            `Slide ${i + 1}`,
        ),
        resize: (box) => {
          document.body.style.boxSizing = "border-box";
          document.body.style.paddingTop = `${box.top}px`;
          document.body.style.paddingBottom = `${box.bottom}px`;
        },
      };
      if (sections.length)
        adapter.go(
          Math.min(
            sections.length - 1,
            Math.max(0, (parseInt(location.hash.slice(1), 10) || 1) - 1),
          ),
        );
    }
    // Hide legacy player UI only after its content adapter is available.
    const hide = document.createElement("style");
    hide.textContent = `${canonical || policy || canvas ? ".ui,.presenter-controls,#slide-picker-toggle,#slide-picker,#slide-nav-bar,#slide-drawer,#slide-drawer-backdrop{display:none!important}" : ""}[data-slide][hidden]{display:none!important}@media print{slides-player{display:none!important}}`;
    document.head.append(hide);
    const host = document.createElement("slides-player");
    host.style.cssText =
      "position:fixed;inset:0;z-index:1000;pointer-events:none;";
    const root = host.attachShadow({ mode: "open" });
    root.innerHTML = `<style>
:host{font:14px/1.4 system-ui,sans-serif;color:#edf3fb;color-scheme:dark}*{box-sizing:border-box}button,a{font:600 14px/1.3 system-ui,sans-serif;min-height:44px;min-width:44px;padding:9px 13px;border:1px solid #405875;border-radius:10px;color:#edf3fb;background:#20334b;text-decoration:none;cursor:pointer}button:hover,a:hover{background:#2a445f}button:disabled{opacity:.4;cursor:default}button:focus-visible,a:focus-visible{outline:3px solid #7de0ce;outline-offset:3px}button[aria-current=true]{border-color:#7de0ce;background:#203f4c}header,footer{position:absolute;left:0;right:0;pointer-events:auto;background:#101c2ef5;border-color:#34475f;border-style:solid;backdrop-filter:blur(12px)}header{top:0;display:flex;align-items:center;gap:12px;padding:8px 12px;border-width:0 0 1px;padding-top:max(8px,env(safe-area-inset-top))}.title{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#b7c8de}footer{bottom:0;display:grid;justify-content:center;gap:6px;padding:8px 12px;border-width:1px 0 0;padding-bottom:max(8px,env(safe-area-inset-bottom))}.navigation{display:flex;align-items:center;justify-content:center;gap:10px}.counter{min-width:88px;text-align:center;font-weight:600;font-variant-numeric:tabular-nums}.actions{display:flex;gap:6px;justify-content:center}.step{font-size:12px;color:#a9bdd4;min-width:70px;align-self:center;text-align:center}.actions button{padding:8px;font-size:20px}.status{margin:0;text-align:center;color:#a9bdd4;max-width:70ch}dialog{pointer-events:auto;width:min(1000px,calc(100% - 24px));max-height:calc(100dvh - 24px);border:1px solid #405875;border-radius:16px;padding:0;background:#101c2e;color:#edf3fb;box-shadow:0 20px 80px #0009}dialog[open]{display:flex;flex-direction:column}dialog::backdrop{background:#040c18b8}.picker-header{display:flex;gap:12px;align-items:center;flex-wrap:wrap;flex-shrink:0;padding:16px;border-bottom:1px solid #34475f}.picker-header h2{flex:1;margin:0;font-size:21px}.shortcuts{display:flex;width:100%;gap:10px}.shortcuts button{flex:1}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px;padding:16px;overflow:auto;overscroll-behavior:contain;min-height:0}.card{display:flex;flex-direction:column;gap:8px;min-width:0;padding:9px;text-align:left;font-weight:500;border-width:2px}.picture{aspect-ratio:16/9;background:#09111f;border-radius:5px;overflow:hidden;display:grid;place-items:center;font-size:30px;color:#8da4c3}.picture img{width:100%;height:100%;object-fit:contain;grid-area:1/1}.picture span{grid-area:1/1}.card-label{overflow-wrap:anywhere}@media(max-width:400px){header{padding-left:8px;padding-right:8px;gap:8px}.title{font-size:12px}.navigation{gap:6px}.navigation button{padding:8px 10px}.counter{min-width:82px}.grid{padding:12px}.step{min-width:60px}}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto}}
</style><header aria-label="Presentation player"><button id="slides" aria-label="Open slide thumbnails" aria-haspopup="dialog">☰ Slides</button><span class="title"></span></header><footer aria-label="Playback controls"><div class="navigation"><button id="previous" aria-label="Previous">← Previous</button><span class="counter" role="status"></span><button id="next" aria-label="Next">Next →</button></div><div class="actions"><button id="replay" aria-label="Replay slide" title="Replay slide">↻</button><button id="play" aria-label="Play animations" title="Play animations">▶</button><span class="step"></span><button id="sources" aria-label="Sources" title="Sources">ⓘ</button><button id="fullscreen" aria-label="Full screen" title="Full screen">⛶</button></div><p class="status" role="status" hidden></p></footer><dialog aria-labelledby="picker-title"><div class="picker-header"><h2 id="picker-title">Jump to slide</h2><button id="close" aria-label="Close slide thumbnails">×</button><div class="shortcuts"><button id="first">First slide</button><button id="last">Last slide →</button></div></div><div class="grid" role="group" aria-label="Presentation slides"></div></dialog>`;
    document.body.append(host);
    if (typeof adapter.download === "string") {
      try {
        const url = new URL(adapter.download, location.href);
        if (url.origin === location.origin) {
          const link = document.createElement("a");
          link.href = url.href;
          link.download = "";
          link.textContent = "Download";
          link.id = "download-pptx";
          root.querySelector("header").append(link);
        }
      } catch {}
    }
    const $ = (selector) => root.querySelector(selector),
      picker = $("dialog");
    let cards = [],
      signature = "",
      positionSignature = "",
      pending = null;
    const controller = {
      getState() {
        let s;
        try {
          s = adapter.getState();
        } catch {
          return null;
        }
        if (
          !s ||
          !Number.isInteger(s.count) ||
          s.count < 1 ||
          s.count > 10000 ||
          !Number.isInteger(s.index) ||
          s.index < 0 ||
          s.index >= s.count
        )
          return null;
        const steps = Number.isInteger(s.steps)
          ? Math.min(10000, Math.max(1, s.steps))
          : 1;
        return {
          ...s,
          step: Number.isInteger(s.step)
            ? Math.max(0, Math.min(steps - 1, s.step))
            : 0,
          steps,
        };
      },
      go(n) {
        const s = this.getState();
        if (!s) {
          pending = n;
          return;
        }
        adapter.go(Math.max(0, Math.min(s.count - 1, n)));
        sync();
      },
      next() {
        const s = this.getState();
        if (!s || (s.index === s.count - 1 && s.step >= s.steps - 1)) return;
        if (adapter.next) adapter.next();
        else this.go(s.index + 1);
        sync();
      },
      previous() {
        const s = this.getState();
        if (!s || (s.index === 0 && s.step === 0)) return;
        if (adapter.previous) adapter.previous();
        else this.go(s.index - 1);
        sync();
      },
    };
    window.slidesPlayerController = controller;
    function resize() {
      const top = $("header").getBoundingClientRect().height,
        bottom = $("footer").getBoundingClientRect().height;
      const stage = document.querySelector("[data-slides-stage]");
      if (stage && !adapter.resize)
        Object.assign(stage.style, {
          position: "fixed",
          left: "0",
          right: "0",
          top: `${top}px`,
          bottom: `${bottom}px`,
        });
      adapter.resize?.({
        top,
        bottom,
        width: innerWidth,
        height: Math.max(1, innerHeight - top - bottom),
      });
    }
    function buildCards(s) {
      const titles = Array.isArray(adapter.titles) ? adapter.titles : [],
        thumbs = Array.isArray(adapter.thumbnails) ? adapter.thumbnails : [];
      const nextSignature = JSON.stringify([s.count, titles, thumbs]);
      if (nextSignature === signature) return;
      signature = nextSignature;
      $(".grid").replaceChildren();
      cards = [];
      for (let i = 0; i < s.count; i++) {
        const label =
          typeof titles[i] === "string" ? titles[i] : `Slide ${i + 1}`;
        const button = document.createElement("button");
        button.className = "card";
        button.setAttribute("aria-label", `Slide ${i + 1}: ${label}`);
        const picture = document.createElement("span");
        picture.className = "picture";
        const fallback = document.createElement("span");
        fallback.textContent = String(i + 1);
        picture.append(fallback);
        if (typeof thumbs[i] === "string") {
          try {
            const url = new URL(thumbs[i], location.href);
            if (url.origin === location.origin) {
              const image = document.createElement("img");
              image.alt = "";
              image.loading = "lazy";
              image.src = url.href;
              image.onload = () => fallback.remove();
              image.onerror = () => image.remove();
              picture.append(image);
            }
          } catch {
            /* A numbered card remains usable without an image. */
          }
        }
        const text = document.createElement("span");
        text.className = "card-label";
        text.textContent = `${i + 1}. ${label}`;
        button.append(picture, text);
        button.onclick = () => {
          controller.go(i);
          picker.close();
        };
        $(".grid").append(button);
        cards.push(button);
      }
    }
    function sync() {
      const s = controller.getState();
      $("#slides").disabled = !s;
      $("#previous").disabled = !s || (s.index === 0 && s.step === 0);
      $("#next").disabled =
        !s || (s.index === s.count - 1 && s.step >= s.steps - 1);
      $("#replay").disabled = !s;
      $("#play").disabled = !s || !adapter.play;
      $("#sources").disabled = !adapter.sources;
      $(".counter").textContent = s
        ? `Slide ${s.index + 1} / ${s.count}`
        : "Loading…";
      $(".step").textContent =
        s && s.steps > 1 ? `Step ${s.step + 1} / ${s.steps}` : "";
      $("#play").textContent = s?.playing ? "Ⅱ" : "▶";
      $("#play").setAttribute(
        "aria-label",
        s?.playing ? "Pause animations" : "Play animations",
      );
      if (!s) return;
      if (pending !== null) {
        const target = pending;
        pending = null;
        controller.go(target);
        return;
      }
      buildCards(s);
      cards.forEach((card, i) =>
        card.setAttribute("aria-current", String(i === s.index)),
      );
      $(".title").textContent = adapter.titles?.[s.index] || document.title;
      const value = `${s.index}/${s.count}/${s.step}/${s.steps}`;
      if (value !== positionSignature) {
        positionSignature = value;
        dispatchEvent(new Event("slides-position-change"));
      }
    }
    $("#slides").onclick = () => {
      adapter.pause?.();
      sync();
      picker.showModal();
      cards[controller.getState()?.index || 0]?.focus({ preventScroll: true });
      cards[controller.getState()?.index || 0]?.scrollIntoView({
        block: "nearest",
      });
    };
    $("#close").onclick = () => picker.close();
    picker.addEventListener("close", () => $("#slides").focus());
    $("#first").onclick = () => {
      controller.go(0);
      picker.close();
    };
    $("#last").onclick = () => {
      const s = controller.getState();
      if (s) controller.go(s.count - 1);
      picker.close();
    };
    $("#next").onclick = () => controller.next();
    $("#previous").onclick = () => controller.previous();
    $("#replay").onclick = () => {
      if (adapter.replay) adapter.replay();
      else controller.go(controller.getState()?.index || 0);
      sync();
    };
    $("#play").onclick = () => {
      adapter.play?.();
      sync();
    };
    $("#sources").onclick = () => adapter.sources?.();
    $("#fullscreen").onclick = () => {
      const result = document.fullscreenElement
        ? document.exitFullscreen()
        : document.documentElement.requestFullscreen?.();
      result?.catch(() => {
        $(".status").hidden = false;
        $(".status").textContent =
          "Full screen is unavailable in this browser.";
      });
    };
    function keys(event) {
      // Capture before legacy deck listeners, including inside the player's shadow tree.
      const path = event.composedPath(),
        editing = path.some(
          (node) =>
            node instanceof Element &&
            node.matches("input,textarea,select,[contenteditable=true]"),
        );
      if (picker.open || document.querySelector("dialog[open]")) {
        if (
          [
            "ArrowRight",
            "ArrowLeft",
            "PageDown",
            "PageUp",
            "Home",
            "End",
            " ",
            "p",
            "r",
            "f",
            "s",
          ].includes(event.key)
        )
          event.stopImmediatePropagation();
        return;
      }
      if (
        editing ||
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        ([" ", "Enter"].includes(event.key) &&
          path.some(
            (node) => node instanceof Element && node.matches("button,a"),
          ))
      )
        return;
      let action;
      if (["ArrowRight", "PageDown", " "].includes(event.key))
        action = () => controller.next();
      else if (["ArrowLeft", "PageUp", "Backspace"].includes(event.key))
        action = () => controller.previous();
      else if (event.key === "Home") action = () => controller.go(0);
      else if (event.key === "End")
        action = () => {
          const s = controller.getState();
          if (s) controller.go(s.count - 1);
        };
      else if (event.key.toLowerCase() === "r")
        action = () => $("#replay").click();
      else if (event.key.toLowerCase() === "p")
        action = () => $("#play").click();
      else if (event.key.toLowerCase() === "f")
        action = () => $("#fullscreen").click();
      else if (event.key.toLowerCase() === "s")
        action = () => $("#sources").click();
      if (action) {
        event.preventDefault();
        event.stopImmediatePropagation();
        action();
      }
    }
    window.addEventListener("keydown", keys, true);
    function contentTarget(event) {
      if (picker.open || document.querySelector("dialog[open]")) return null;
      const path = event.composedPath();
      if (
        path.includes(host) ||
        path.some(
          (node) =>
            node instanceof Element &&
            node.matches(
              "a,button,input,select,textarea,summary,[contenteditable=true]",
            ),
        )
      )
        return null;
      return path.find(
        (node) =>
          node instanceof Element &&
          node.matches("[data-slides-stage],[data-slide],#stage,#slide"),
      );
    }
    window.addEventListener(
      "click",
      (event) => {
        const stage = contentTarget(event);
        if (!stage) return;
        event.stopImmediatePropagation();
        const rect = stage.getBoundingClientRect();
        if (event.clientX < rect.left + rect.width / 2) controller.previous();
        else controller.next();
      },
      true,
    );
    let touch;
    window.addEventListener(
      "touchstart",
      (event) => {
        if (!contentTarget(event) || event.touches.length !== 1) return;
        touch = { x: event.touches[0].clientX, y: event.touches[0].clientY };
        event.stopImmediatePropagation();
      },
      { capture: true, passive: true },
    );
    window.addEventListener(
      "touchend",
      (event) => {
        if (!touch) return;
        const dx = event.changedTouches[0].clientX - touch.x,
          dy = event.changedTouches[0].clientY - touch.y;
        touch = null;
        if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy)) {
          event.preventDefault();
          event.stopImmediatePropagation();
          if (dx < 0) controller.next();
          else controller.previous();
        }
      },
      { capture: true, passive: false },
    );
    window.addEventListener(
      "touchcancel",
      () => {
        touch = null;
      },
      { capture: true, passive: true },
    );

    // Reserve the same toolbar space for every format, including on rotation/fullscreen.
    const observer = new ResizeObserver(resize);
    observer.observe($("header"));
    observer.observe($("footer"));
    addEventListener("resize", resize);
    document.addEventListener("fullscreenchange", resize);
    addEventListener("slides-change", () => {
      sync();
      resize();
    });
    addEventListener("hashchange", sync);
    setInterval(sync, 250);
    sync();
    resize();
    dispatchEvent(new Event("slides-player-ready"));
  }
  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
