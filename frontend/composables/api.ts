import { inject } from "vue";
export const csrfKey = Symbol("csrf");
export function useCsrf(): string {
  return inject<string>(csrfKey, "");
}
export function formData(
  values: Record<string, string | number | string[]>,
): FormData {
  const form = new FormData();
  for (const [key, value] of Object.entries(values)) {
    for (const item of Array.isArray(value) ? value : [value])
      form.append(key, String(item));
  }
  return form;
}
export async function request<T>(
  url: string,
  body?: FormData,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(url, {
    method: body ? "POST" : "GET",
    body,
    signal,
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  if (!response.headers.get("Content-Type")?.includes("application/json"))
    throw new Error(
      "Your session may have expired. Refresh and sign in again.",
    );
  const result = await response.json();
  if (!response.ok)
    throw new Error(
      typeof result.error === "string"
        ? result.error
        : "Could not complete this request. Please try again.",
    );
  return result as T;
}
export function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "Connection interrupted. Please try again.";
}
export function localDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? value
    : new Intl.DateTimeFormat("en-GB", {
        day: "numeric",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        timeZoneName: "short",
      }).format(date);
}
export function pathFor(
  endpoint: string,
  name: string,
  filename?: string,
  revision?: number | null,
): string {
  const prefix = revision ? `/r/${revision}` : "";
  return `${prefix}/${endpoint}/${encodeURIComponent(name)}${filename ? "/" + filename.split("/").map(encodeURIComponent).join("/") : ""}`;
}
