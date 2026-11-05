export type SortMode =
  "name-asc" | "name-desc" | "modified-desc" | "modified-asc";
export type Version = "latest" | "fixed";
export interface FileEntry {
  name: string;
  format: string;
  url: string;
  preview_url: string | null;
  size: number;
}
export interface Deck {
  name: string;
  title: string;
  description: string;
  files: FileEntry[];
  format_files: Partial<Record<"html" | "pptx" | "pdf", string>>;
  linked_formats: boolean;
  updated_iso: string;
  updated_label: string;
  tags: string[];
  revision: number | null;
  thumbnail: string;
}
export interface LibraryDeck extends Deck {
  favorite: number;
  pinned: number;
}
export interface LibraryData {
  entries: LibraryDeck[];
  count: number;
  all_tags: string[];
}
export interface UploadData {
  entries: Deck[];
  deck: string;
}
export interface Revision {
  id: number;
  created: string;
  modified: string;
  files: { name: string; bytes: number; url: string }[];
}
export interface HistoryData {
  entry: Deck;
  revisions: Revision[];
  selected: string;
  live: boolean;
}
export interface SearchData {
  query: string;
  results: {
    title: string;
    filename: string;
    page: number;
    snippet: string;
    url: string;
  }[];
  total: number;
  page: number;
  pending: boolean;
  tags: string[];
  all_tags: string[];
  favorites: boolean;
}
export interface Share {
  id: number;
  deck: string;
  title: string;
  created: string;
  created_iso: string;
  expires: string;
  expires_iso: string;
  active: boolean;
  status: "Active" | "Expired" | "Revoked";
  revision: number | null;
  views: number;
  last_opened: string;
}
export interface SharesData {
  rows: Share[];
  link: string | null;
}
export interface ViewerData {
  name: string;
  filename: string;
  revision: number | null;
  title: string;
  source: string;
  formats: { html?: string; pptx?: string; download_pptx?: string };
  active_format: string;
  presenter_url: string;
}
export interface PresenterData {
  entry: Deck;
  filename: string;
  notes: string;
  channel: string;
  supported: boolean;
  audience: string;
  source: string;
}
export type Page =
  | "library"
  | "upload"
  | "history"
  | "search"
  | "shares"
  | "viewer"
  | "presenter";
export interface Bootstrap {
  page: Page;
  csrf: string;
  data: Record<string, unknown>;
}
