"use client";

import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { createJob } from "@/lib/api";

type Mode = "scrape" | "crawl";

export default function DashboardPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("scrape");
  const [url, setUrl] = useState("");
  const [maxPages, setMaxPages] = useState(10);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleSubmit() {
    const trimmed = url.trim();
    if (!trimmed || loading) return;
    if (!trimmed.startsWith("http://") && !trimmed.startsWith("https://")) {
      setError("URL must start with http:// or https://");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const job = await createJob({
        url: trimmed,
        fetcher_type: "auto",
        max_pages: mode === "crawl" ? maxPages : 1,
      });
      router.push(`/jobs/${job.id}`);
    } catch (err: unknown) {
      const e = err as { body?: { detail?: string | { message?: string } }; message?: string };
      const detail = e.body?.detail;
      if (detail && typeof detail === "object" && detail.message) {
        setError(detail.message);
      } else if (typeof detail === "string") {
        setError(detail);
      } else {
        setError("Failed to start job.");
      }
      setLoading(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", alignItems: "center", justifyContent: "center", padding: "40px 32px" }}>

      {/* Heading */}
      <h1 style={{ fontSize: "42px", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.03em", lineHeight: 1.1, textAlign: "center", marginBottom: "10px" }}>
        Extract anything.
      </h1>
      <p style={{ fontSize: "18px", fontWeight: 400, color: "var(--text-secondary)", letterSpacing: "-0.02em", textAlign: "center", marginBottom: "32px" }}>
        Scrape or crawl any URL and get structured data instantly.
      </p>

      {/* Input card */}
      <div style={{ width: "100%", maxWidth: "580px", background: "var(--surface)", borderRadius: "16px", border: "1px solid var(--border)", boxShadow: "0 2px 16px rgba(0,0,0,0.07)", overflow: "hidden" }}>

        {/* URL row */}
        <div style={{ display: "flex", alignItems: "center", gap: "10px", padding: "14px 16px", borderBottom: "1px solid var(--border)" }}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0, color: "var(--text-muted)" }}>
            <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.3" />
            <path d="M8 1.5C8 1.5 5.5 4 5.5 8s2.5 6.5 2.5 6.5M8 1.5C8 1.5 10.5 4 10.5 8s-2.5 6.5-2.5 6.5M1.5 8h13" stroke="currentColor" strokeWidth="1.3" />
          </svg>
          <input
            ref={inputRef}
            type="url"
            value={url}
            onChange={(e) => { setUrl(e.target.value); setError(null); }}
            placeholder="https://example.com"
            disabled={loading}
            autoFocus
            style={{ flex: 1, border: "none", outline: "none", fontSize: "15px", color: "var(--text-primary)", background: "transparent", fontFamily: "inherit" }}
            onKeyDown={(e) => { if (e.key === "Enter") handleSubmit(); }}
          />
        </div>

        {/* Mode row */}
        <div style={{ display: "flex", alignItems: "center", padding: "10px 12px", gap: "4px" }}>
          {(["scrape", "crawl"] as Mode[]).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              style={{
                display: "flex", alignItems: "center", gap: "6px",
                padding: "6px 14px", fontSize: "13px", fontWeight: mode === m ? 500 : 400,
                background: mode === m ? "var(--text-primary)" : "transparent",
                color: mode === m ? "#fff" : "var(--text-secondary)",
                border: "1px solid", borderColor: mode === m ? "var(--text-primary)" : "var(--border)",
                borderRadius: "7px", cursor: "pointer", transition: "all 0.15s",
              }}
            >
              {m === "scrape" ? (
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                  <rect x="1" y="1" width="10" height="10" rx="1.5" stroke="currentColor" strokeWidth="1.2" />
                  <path d="M3 4h6M3 6h4M3 8h5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
                </svg>
              ) : (
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                  <circle cx="6" cy="6" r="1.8" stroke="currentColor" strokeWidth="1.2" />
                  <path d="M6 1v1.5M6 9.5V11M1 6h1.5M9.5 6H11M2.5 2.5l1 1M8.5 8.5l1 1M9.5 2.5l-1 1M3.5 8.5l-1 1" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
                </svg>
              )}
              {m === "scrape" ? "Scrape" : "Crawl"}
            </button>
          ))}

          {/* Max pages (crawl only) */}
          {mode === "crawl" && (
            <div style={{ display: "flex", alignItems: "center", gap: "6px", marginLeft: "6px" }}>
              <span style={{ fontSize: "12px", color: "var(--text-muted)", whiteSpace: "nowrap" }}>Max Pages</span>
              <input
                type="number"
                min={1}
                max={100}
                value={maxPages}
                onChange={(e) => setMaxPages(Math.max(1, Math.min(100, parseInt(e.target.value) || 1)))}
                style={{
                  width: "48px", padding: "4px 6px", fontSize: "12px",
                  border: "1px solid var(--border)", borderRadius: "6px",
                  background: "var(--page-bg)", color: "var(--text-primary)",
                  outline: "none", fontFamily: "inherit", textAlign: "center",
                }}
                onFocus={e => (e.target.style.borderColor = "var(--border-strong)")}
                onBlur={e => (e.target.style.borderColor = "var(--border)")}
              />
            </div>
          )}

          {/* Spacer */}
          <div style={{ flex: 1 }} />

          {/* Submit */}
          <button
            onClick={handleSubmit}
            disabled={loading || !url.trim()}
            style={{
              width: "36px", height: "36px", borderRadius: "50%", border: "none", flexShrink: 0,
              background: loading || !url.trim() ? "var(--border-strong)" : "var(--lime)",
              color: "#111", display: "flex", alignItems: "center", justifyContent: "center",
              cursor: loading || !url.trim() ? "not-allowed" : "pointer", transition: "background 0.15s",
            }}
          >
            {loading ? (
              <span style={{ width: "13px", height: "13px", border: "2px solid rgba(255,255,255,0.4)", borderTopColor: "#fff", borderRadius: "50%", display: "inline-block", animation: "spin 0.6s linear infinite" }} />
            ) : (
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M2 7h10M7 2l5 5-5 5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div style={{ marginTop: "12px", padding: "8px 12px", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: "8px", fontSize: "13px", color: "#dc2626", maxWidth: "580px", width: "100%" }}>
          {error}
        </div>
      )}

      {/* Mode description */}
      <p style={{ marginTop: "16px", fontSize: "12.5px", color: "var(--text-muted)", textAlign: "center" }}>
        {mode === "scrape"
          ? "Scrape extracts data from the provided URL only."
          : `Crawl follows links and extracts data from up to ${maxPages} page${maxPages !== 1 ? "s" : ""}.`}
      </p>

    </div>
  );
}
