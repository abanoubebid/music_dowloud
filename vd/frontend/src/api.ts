export interface Platform { id: string; name: string }
export interface AudioOpt { id: string; label: string; detail: string }
export interface Entry { index: number; title: string; duration: number | null; thumbnail: string | null; available: boolean }
export interface Analysis { analysis_id: string; kind: "single" | "playlist"; title: string | null; thumbnail: string | null; duration: number | null; uploader: string | null; has_playlist: boolean; heights: number[]; containers: Record<string, string>; audio: AudioOpt[]; entries: Entry[]; max_playlist_items: number }
export interface Ticket { token: string; filename: string }

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { ...init, headers: { "Content-Type": "application/json" } });
  if (!r.ok) { const b = await r.json().catch(() => ({})); throw new Error(b.detail ?? "Request failed."); }
  return r.json();
}
export const api = {
  platforms: () => req<Platform[]>("/api/platforms"),
  analyze: (platform: string, url: string, scope: "auto" | "playlist" = "auto") => req<Analysis>("/api/analyze", { method: "POST", body: JSON.stringify({ platform, url, scope }) }),
  start: (b: { analysis_id: string; kind: string; quality: string; entries: number[] | null }) => req<{ items: Ticket[] }>("/api/download", { method: "POST", body: JSON.stringify(b) }),
  streamUrl: (token: string, dl: string) => `/api/stream/${token}?dl=${dl}`,
};
