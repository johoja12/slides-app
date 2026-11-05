import { onBeforeUnmount, onMounted, ref } from "vue";
export interface Position {
  type: "position";
  index: number;
  count: number;
}
export type PresentationMessage =
  Position | { type: "navigate"; index: number } | { type: "hello" };
export function validPosition(value: unknown): value is Position {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<Position>;
  return (
    item.type === "position" &&
    Number.isInteger(item.index) &&
    Number.isInteger(item.count) &&
    item.index! >= 0 &&
    item.count! > 0 &&
    item.index! < item.count! &&
    item.count! <= 10000
  );
}
export function usePresentationChannel(
  channel: string,
  receive: (value: PresentationMessage) => void,
) {
  let bus: BroadcastChannel | undefined;
  const supported = ref(typeof BroadcastChannel !== "undefined");
  onMounted(() => {
    if (supported.value) {
      bus = new BroadcastChannel("slides-" + channel);
      bus.onmessage = (event) => {
        const value: unknown = event.data;
        if (!value || typeof value !== "object") return;
        const item = value as PresentationMessage;
        if (
          validPosition(value) ||
          item.type === "hello" ||
          (item.type === "navigate" &&
            Number.isInteger(item.index) &&
            item.index >= 0 &&
            item.index < 10000)
        )
          receive(item);
      };
    }
  });
  onBeforeUnmount(() => bus?.close());
  function send(value: PresentationMessage) {
    // Explicit primitives are cloneable even when the caller holds Vue reactive state.
    // Keeping the wire shape narrow also prevents private data from being forwarded.
    if (value.type === "position")
      bus?.postMessage({
        type: "position",
        index: value.index,
        count: value.count,
      });
    else if (value.type === "navigate")
      bus?.postMessage({ type: "navigate", index: value.index });
    else bus?.postMessage({ type: "hello" });
  }
  return { send, supported };
}
export function frameNavigate(
  frame: HTMLIFrameElement | undefined,
  index: number,
) {
  frame?.contentWindow?.postMessage(
    { type: "slides-navigate", index },
    location.origin,
  );
}
