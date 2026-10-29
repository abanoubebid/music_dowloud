import { useEffect, useState } from "react";
import { Download, Search, Loader2, CheckCircle2, AlertCircle, Youtube, ClipboardPaste, Film, Music, ListVideo } from "lucide-react";
import { api, Analysis, Platform } from "./api";

const TAG: Record<number, string> = { 720: "HD", 1080: "Full HD", 1440: "QHD", 2160: "4K", 4320: "8K" };
const dur = (s: number | null) => (s ? `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}` : "");
const rid = () => (globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2) + Date.now().toString(36)).replace(/[^A-Za-z0-9_-]/g, "").slice(0, 40);

// The server sets a short-lived cookie the moment the browser gets the response, i.e. when the download
// actually starts (or the save dialog appears). That is our cue to close the "preparing" popup.
function waitForStart(id: string, timeoutMs = 330_000): Promise<"ok" | "err" | "timeout"> {
  const name = `vd_${id}`;
  return new Promise(resolve => {
    const t0 = Date.now();
    const iv = setInterval(() => {
      const hit = document.cookie.split("; ").find(c => c.startsWith(name + "="));
      if (hit) { clearInterval(iv); document.cookie = `${name}=; Max-Age=0; Path=/`; resolve(hit.endsWith("=ok") ? "ok" : "err"); }
      else if (Date.now() - t0 > timeoutMs) { clearInterval(iv); resolve("timeout"); }
    }, 150);
  });
}

interface Prep { i: number; n: number; name: string }

function Preparing({ p, onHide }: { p: Prep; onHide: () => void }) {
  const [sec, setSec] = useState(0);
  useEffect(() => { setSec(0); const t = setInterval(() => setSec(s => s + 1), 1000); return () => clearInterval(t); }, [p.i]);
  const text = sec < 8 ? "Your browser will start the download (or ask where to save it) in a moment."
    : sec < 25 ? "Still working. High-quality videos need a few more seconds to get ready."
    : "Taking longer than usual. YouTube may be slow to respond or the server is busy.";
  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-labelledby="prep-t">
      <div className="modal">
        <Loader2 className="spin" size={38} />
        <h2 id="prep-t">Preparing your download…</h2>
        {p.n > 1 && <p className="hint">Item {p.i} of {p.n}</p>}
        {p.name && <p className="fname" dir="auto">{p.name}</p>}
        <div className="bar"><i /></div>
        <p className="hint" aria-live="polite">{text}</p>
        <button className="ghost" onClick={onHide}>Hide</button>
      </div>
    </div>
  );
}

function PlatformSelector({ items, value, onChange }: { items: Platform[]; value: string; onChange: (id: string) => void }) {
  return <div className="chips" role="radiogroup" aria-label="Platform">{items.map(p =>
    <button key={p.id} role="radio" aria-checked={p.id === value} className={"chip pill" + (p.id === value ? " on" : "")} onClick={() => onChange(p.id)}><Youtube size={16} /> {p.name}</button>)}</div>;
}

export default function App() {
  const [platforms, setPlatforms] = useState<Platform[]>([]);
  const [platform, setPlatform] = useState("");
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [a, setA] = useState<Analysis | null>(null);
  const [mode, setMode] = useState<"all" | "choose" | null>(null);
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [kind, setKind] = useState<"video" | "audio">("video");
  const [quality, setQuality] = useState("");
  const [starting, setStarting] = useState(false);
  const [notice, setNotice] = useState("");
  const [prep, setPrep] = useState<Prep | null>(null);
  const [hidden, setHidden] = useState(false);

  useEffect(() => { api.platforms().then(p => { setPlatforms(p); setPlatform(p[0]?.id ?? ""); }).catch(e => setError(e.message)); }, []);

  const analyze = async (scope: "auto" | "playlist" = "auto") => {
    if (busy || !url.trim()) return;
    setBusy(true); setError(""); setNotice(""); setA(null); setMode(null); setQuality(""); setPicked(new Set());
    try { setA(await api.analyze(platform, url, scope)); } catch (e) { setError((e as Error).message); }
    setBusy(false);
  };
  const paste = async () => { try { setUrl(await navigator.clipboard.readText()); } catch { /* clipboard blocked */ } };
  const switchKind = (k: "video" | "audio") => { setKind(k); setQuality(""); };
  const ready = !!a && (a.kind === "single" || mode === "all" || (mode === "choose" && picked.size > 0));

  const start = async () => {
    if (!a || !quality || starting) return;
    setStarting(true); setError(""); setNotice(""); setHidden(false); setPrep({ i: 1, n: 1, name: "" });
    try {
      const r = await api.start({ analysis_id: a.analysis_id, kind, quality, entries: a.kind === "playlist" && mode === "choose" ? [...picked] : null });
      const n = r.items.length;
      for (let i = 0; i < n; i++) { // one at a time: wait until the browser has really started each file
        const it = r.items[i], id = rid();
        setPrep({ i: i + 1, n, name: it.filename });
        const started = waitForStart(id);
        const el = document.createElement("a"); el.href = api.streamUrl(it.token, id); el.download = it.filename;
        document.body.appendChild(el); el.click(); el.remove();
        const res = await started;
        if (res === "err") throw new Error("This download could not be started. Check the video and try again.");
        if (res === "timeout") throw new Error("The download took too long to start. Please try again.");
      }
      setNotice(n > 1 ? `${n} downloads started. Check your browser's download list.` : "Download started. Check your browser's download list.");
    } catch (e) { setError((e as Error).message); }
    setPrep(null); setStarting(false);
  };

  return (
    <div className="page">
      {prep && !hidden && <Preparing p={prep} onHide={() => setHidden(true)} />}
      <header className="top"><span className="logo"><Download size={18} /></span><b>Media Saver</b></header>
      <main className="wrap">
        <section className="panel">
          <label className="lbl">Platform</label>
          <PlatformSelector items={platforms} value={platform} onChange={setPlatform} />
          <h1>Download video or audio</h1>
          <label className="lbl" htmlFor="u">Video URL</label>
          <form className="url" onSubmit={e => { e.preventDefault(); analyze(); }}>
            <input id="u" value={url} onChange={e => setUrl(e.target.value)} placeholder="Paste a video or playlist URL..." autoComplete="off" />
            <button type="button" className="ghost" onClick={paste} title="Paste" aria-label="Paste"><ClipboardPaste size={16} /></button>
            <button className="primary" disabled={busy || !url.trim()}>{busy ? <Loader2 className="spin" size={16} /> : <Search size={16} />} Analyze</button>
          </form>
          {error && <div className="msg bad" role="alert"><AlertCircle size={16} /> {error}</div>}
        </section>

        {a && <section className="panel">
          <div className="media">
            {a.thumbnail && <img src={a.thumbnail} alt="" />}
            <div className="info"><b dir="auto">{a.title}</b>
              <div className="meta">{a.uploader && <span>{a.uploader}</span>}{a.duration ? <span>{dur(a.duration)}</span> : null}{a.kind === "playlist" && <span><ListVideo size={13} /> {a.entries.length} videos</span>}</div></div>
          </div>
          {a.kind === "single" && a.has_playlist && <button className="link" onClick={() => analyze("playlist")}>This link is part of a playlist — use the playlist instead</button>}

          {a.kind === "playlist" && <>
            <p className="q">How would you like to download this playlist?</p>
            <div className="seg"><button className={mode === "all" ? "on" : ""} onClick={() => setMode("all")}>Download Entire Playlist</button><button className={mode === "choose" ? "on" : ""} onClick={() => setMode("choose")}>Choose Videos</button></div>
            {a.entries.length >= a.max_playlist_items && <p className="hint">Limit: only the first {a.max_playlist_items} items are loaded.</p>}
            {mode === "choose" && <>
              <div className="tools"><button className="ghost" onClick={() => setPicked(new Set(a.entries.filter(e => e.available).map(e => e.index)))}>Select All</button><button className="ghost" onClick={() => setPicked(new Set())}>Deselect All</button><span className="hint">{picked.size} selected</span></div>
              <ul className="list">{a.entries.map(e => <li key={e.index}><label className={e.available ? "" : "off"}>
                <input type="checkbox" disabled={!e.available} checked={picked.has(e.index)} onChange={() => { const n = new Set(picked); n.has(e.index) ? n.delete(e.index) : n.add(e.index); setPicked(n); }} />
                {e.thumbnail && <img src={e.thumbnail} alt="" />}<span className="t" dir="auto">{e.title}{!e.available && " (unavailable)"}</span><span className="hint">{dur(e.duration)}</span></label></li>)}</ul></>}
          </>}

          {ready && <>
            <label className="lbl">Format</label>
            <div className="seg">
              <button className={kind === "video" ? "on" : ""} onClick={() => switchKind("video")}><Film size={16} /> Video</button>
              <button className={kind === "audio" ? "on" : ""} onClick={() => switchKind("audio")}><Music size={16} /> Audio</button>
            </div>
            <label className="lbl">{kind === "video" ? "Quality" : "Audio format"}</label>
            {a.kind === "playlist" && kind === "video" && <p className="hint">Qualities are based on the first video; items without one will fail.</p>}
            {kind === "video" ? (a.heights.length === 0 ? <p className="hint">No compatible video formats found.</p> :
              <div className="chips grid">{a.heights.map(h => <button key={h} className={"chip" + (quality === String(h) ? " on" : "")} onClick={() => setQuality(String(h))}>
                <b>{h}p</b><small>{[TAG[h], `.${a.containers[String(h)]}`].filter(Boolean).join(" · ")}</small></button>)}</div>) :
              <>
                {a.audio.length === 0 ? <p className="hint">No compatible audio formats found.</p> :
                  <div className="chips grid wide">{a.audio.map(o => <button key={o.id} className={"chip" + (quality === o.id ? " on" : "")} onClick={() => setQuality(o.id)}>
                    <b>{o.label}</b><small>{o.detail}</small></button>)}</div>}
                <p className="hint">Original formats are saved as-is. MP3 is re-encoded, so higher bitrates don't add quality.</p>
              </>}
            <button className="primary big" disabled={!quality || starting} onClick={start}>{starting ? <Loader2 className="spin" size={18} /> : <Download size={18} />} Download</button>
            {notice && <div className="msg ok"><CheckCircle2 size={16} /> {notice}</div>}
          </>}
        </section>}
      </main>
    </div>
  );
}
