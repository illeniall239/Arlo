"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createJob, createBatchJob } from "@/lib/api";

const inputStyle: React.CSSProperties = {
  width: "100%",
  border: "1px solid var(--border)",
  borderRadius: "6px",
  padding: "8px 10px",
  fontSize: "13.5px",
  color: "var(--text-primary)",
  background: "var(--surface)",
  outline: "none",
  transition: "border-color 0.15s",
  fontFamily: "inherit",
};

const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: "12px",
  fontWeight: 500,
  color: "var(--text-secondary)",
  marginBottom: "6px",
  letterSpacing: "0.01em",
};

export default function NewJobForm() {
  const router = useRouter();
  const [batch, setBatch] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [url, setUrl] = useState("");
  const [urlsText, setUrlsText] = useState("");
  const [maxPages, setMaxPages] = useState(5);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (batch) {
        const urls = urlsText
          .split("\n")
          .map((u) => u.trim())
          .filter(Boolean);
        const res = await createBatchJob({ prompt, urls, fetcher_type: "auto", max_pages: maxPages });
        window.dispatchEvent(new Event("arlo:new-run"));
        router.push(`/jobs/batch/${res.batch_id}`);
      } else {
        const job = await createJob({ prompt, url, fetcher_type: "auto", max_pages: maxPages });
        window.dispatchEvent(new Event("arlo:new-run"));
        router.push(`/jobs/${job.id}`);
      }
    } catch (err: unknown) {
      const e = err as { body?: { detail?: string | { message?: string } }; message?: string };
      const detail = e.body?.detail;
      if (detail && typeof detail === "object" && detail.message) {
        setError(detail.message);
      } else if (typeof detail === "string") {
        setError(detail);
      } else {
        setError("Failed to create job.");
      }
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>

        {/* Mode toggle */}
        <div style={{ display: "inline-flex", border: "1px solid var(--border)", borderRadius: "6px", overflow: "hidden", alignSelf: "flex-start" }}>
          {[false, true].map((isBatch) => (
            <button
              key={String(isBatch)}
              type="button"
              onClick={() => { setBatch(isBatch); setError(null); }}
              style={{
                padding: "5px 14px",
                fontSize: "12.5px",
                fontWeight: batch === isBatch ? 500 : 400,
                background: batch === isBatch ? "var(--text-primary)" : "transparent",
                color: batch === isBatch ? "var(--surface)" : "var(--text-secondary)",
                border: "none",
                cursor: "pointer",
              }}
            >
              {isBatch ? "Batch" : "Single URL"}
            </button>
          ))}
        </div>

        <div>
          <label style={labelStyle}>What do you want to scrape?</label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder='e.g. "Get all job titles, companies, and salaries"'
            rows={3}
            required
            minLength={10}
            style={{ ...inputStyle, resize: "none", lineHeight: "1.5" }}
            onFocus={e => e.target.style.borderColor = "var(--border-strong)"}
            onBlur={e => e.target.style.borderColor = "var(--border)"}
          />
        </div>

        {batch ? (
          <div>
            <label style={labelStyle}>Target URLs <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>(one per line, max 20)</span></label>
            <textarea
              value={urlsText}
              onChange={(e) => setUrlsText(e.target.value)}
              placeholder={"https://example.com/page1\nhttps://example.com/page2"}
              rows={5}
              required
              style={{ ...inputStyle, resize: "vertical", lineHeight: "1.6" }}
              onFocus={e => e.target.style.borderColor = "var(--border-strong)"}
              onBlur={e => e.target.style.borderColor = "var(--border)"}
            />
            <p style={{ fontSize: "11.5px", color: "var(--text-muted)", marginTop: "4px" }}>
              {urlsText.split("\n").filter((u) => u.trim()).length} URL(s) entered
            </p>
          </div>
        ) : (
          <div>
            <label style={labelStyle}>Target URL</label>
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com"
              required
              style={inputStyle}
              onFocus={e => e.target.style.borderColor = "var(--border-strong)"}
              onBlur={e => e.target.style.borderColor = "var(--border)"}
            />
          </div>
        )}

        <div>
          <label style={labelStyle}>Max pages</label>
          <input
            type="number"
            min={1}
            max={50}
            value={maxPages}
            onChange={(e) => setMaxPages(Math.max(1, Math.min(50, Number(e.target.value))))}
            style={{ ...inputStyle, width: "72px", textAlign: "center" }}
            onFocus={e => e.target.style.borderColor = "var(--border-strong)"}
            onBlur={e => e.target.style.borderColor = "var(--border)"}
          />
        </div>

        {error && (
          <p style={{
            fontSize: "12.5px",
            color: "#b91c1c",
            padding: "8px 10px",
            background: "#fef2f2",
            borderRadius: "5px",
            border: "1px solid #fecaca",
          }}>
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={loading}
          style={{
            background: loading ? "var(--border-strong)" : "var(--accent)",
            color: "#fff",
            border: "none",
            borderRadius: "6px",
            padding: "9px 16px",
            fontSize: "13.5px",
            fontWeight: 500,
            cursor: loading ? "not-allowed" : "pointer",
            fontFamily: "inherit",
            transition: "background 0.15s",
            width: "100%",
          }}
          onMouseEnter={e => { if (!loading) e.currentTarget.style.background = "var(--accent-hover)"; }}
          onMouseLeave={e => { if (!loading) e.currentTarget.style.background = "var(--accent)"; }}
        >
          {loading ? "Starting…" : batch ? "Run batch" : "Run scrape"}
        </button>

      </div>
    </form>
  );
}
