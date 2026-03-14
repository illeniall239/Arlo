"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { cancelJob, fetchJob, fetchJobResults, retryJob } from "@/lib/api";
import { useJobSSE } from "@/hooks/useJobSSE";
import LiveStatusFeed from "@/components/stream/LiveStatusFeed";
import ResultsTable from "@/components/results/ResultsTable";
import { getExportUrl } from "@/lib/api";
import type { JobDetail, ScrapeResult } from "@/types";

const STATUS_DOT: Record<string, string> = {
  completed:   "#c9f135",
  failed:      "#f87171",
  cancelled:   "#6b7280",
  running:     "#60a5fa",
  planning:    "#60a5fa",
  structuring: "#a78bfa",
  pending:     "#fbbf24",
};

function statusLabel(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function formatDuration(s: number) {
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

function getDomain(url: string) {
  try { return new URL(url).hostname.replace("www.", ""); }
  catch { return url; }
}

export default function JobDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id }    = use(params);
  const router    = useRouter();
  const [job, setJob]       = useState<JobDetail | null>(null);
  const [result, setResult] = useState<ScrapeResult | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const { isDone } = useJobSSE(id);

  useEffect(() => {
    fetchJob(id).then(setJob).catch(console.error);
  }, [id]);

  useEffect(() => {
    if (isDone) {
      fetchJob(id).then(setJob).catch(console.error);
      fetchJobResults(id).then(setResult).catch(console.error);
    }
  }, [isDone, id]);

  useEffect(() => {
    if (job?.status === "completed") {
      fetchJobResults(id).then(setResult).catch(() => null);
    }
  }, [job?.status, id]);

  const handleCancel = async () => {
    setActionLoading(true);
    try {
      await cancelJob(id);
      setJob((j) => j ? { ...j, status: "cancelled" } : j);
    } catch {}
    setActionLoading(false);
  };

  const handleRetry = async () => {
    setActionLoading(true);
    try {
      const newJob = await retryJob(id);
      window.location.href = `/jobs/${newJob.id}`;
    } catch {}
    setActionLoading(false);
  };

  if (!job) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "var(--text-muted)", fontSize: "13px" }}>
        Loading…
      </div>
    );
  }

  const isTerminal = ["completed", "failed", "cancelled"].includes(job.status);
  const isRunning  = !isTerminal;
  const duration   = job.completed_at && job.started_at
    ? Math.round((new Date(job.completed_at).getTime() - new Date(job.started_at).getTime()) / 1000)
    : null;
  const dotColor = STATUS_DOT[job.status] ?? "#b4b4ae";
  const domain = getDomain(job.url);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflowY: "auto" }}>

      {/* ── Top nav bar ── */}
      <div style={{ display: "flex", alignItems: "center", gap: "12px", padding: "14px 28px 0", flexShrink: 0 }}>
        <button
          onClick={() => router.push("/history")}
          style={{ display: "flex", alignItems: "center", gap: "5px", background: "none", border: "none", cursor: "pointer", fontSize: "12.5px", color: "var(--text-muted)", padding: 0, fontFamily: "inherit", transition: "color 0.12s" }}
          onMouseEnter={e => (e.currentTarget.style.color = "var(--text-secondary)")}
          onMouseLeave={e => (e.currentTarget.style.color = "var(--text-muted)")}
        >
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
            <path d="M8.5 2L3.5 6.5l5 4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Jobs
        </button>
        <span style={{ color: "var(--border-strong)", fontSize: "13px" }}>/</span>
        <span style={{ fontSize: "12.5px", color: "var(--text-muted)", fontFamily: "var(--font-geist-mono), monospace" }}>{domain}</span>
      </div>

      {/* ── Main content ── */}
      <div style={{ padding: "20px 28px 40px", flex: 1 }}>

        {/* ── Header ── */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "24px", marginBottom: "20px" }}>
          <div style={{ minWidth: 0 }}>
            {/* URL */}
            <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "8px" }}>
              <a
                href={job.url} target="_blank" rel="noopener noreferrer"
                style={{ fontSize: "13px", color: "var(--text-secondary)", fontFamily: "var(--font-geist-mono), monospace", textDecoration: "none", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "480px" }}
                onMouseEnter={e => (e.currentTarget.style.color = "var(--text-primary)")}
                onMouseLeave={e => (e.currentTarget.style.color = "var(--text-secondary)")}
              >
                {job.url}
              </a>
              <svg width="11" height="11" viewBox="0 0 11 11" fill="none" style={{ flexShrink: 0, color: "var(--text-muted)" }}>
                <path d="M4.5 2.5H2a1 1 0 00-1 1v5.5a1 1 0 001 1h5.5a1 1 0 001-1v-2.5M6.5 1H10m0 0v3.5M10 1L5 6" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>

            {/* Status strip */}
            <div style={{ display: "flex", alignItems: "center", gap: "16px", flexWrap: "wrap" }}>
              {/* Status */}
              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <span style={{
                  width: "7px", height: "7px", borderRadius: "50%", background: dotColor, flexShrink: 0,
                  boxShadow: isRunning ? `0 0 0 0 ${dotColor}` : "none",
                  animation: isRunning ? "statusPulse 1.5s ease-out infinite" : "none",
                }} />
                <span style={{ fontSize: "13px", fontWeight: 500, color: "var(--text-primary)" }}>
                  {statusLabel(job.status)}
                </span>
              </div>

              {duration !== null && (
                <StatChip label="duration" value={formatDuration(duration)} />
              )}
              {result && (
                <StatChip label="rows" value={String(result.row_count)} accent />
              )}
              {result?.schema_detected && result.schema_detected.length > 0 && (
                <StatChip label="fields" value={String(result.schema_detected.length)} />
              )}
              {job.fetcher_type && (
                <StatChip label="mode" value={job.fetcher_type} />
              )}
            </div>
          </div>

          {/* Actions */}
          <div style={{ display: "flex", gap: "6px", flexShrink: 0 }}>
            {isRunning && (
              <button
                onClick={handleCancel} disabled={actionLoading}
                style={{ padding: "7px 14px", fontSize: "12.5px", border: "1px solid #fecaca", borderRadius: "8px", background: "transparent", color: "#dc2626", cursor: "pointer", fontFamily: "inherit", fontWeight: 500 }}
              >
                Cancel
              </button>
            )}
            {isTerminal && (
              <button
                onClick={handleRetry} disabled={actionLoading}
                style={{ padding: "7px 16px", fontSize: "12.5px", background: "var(--text-primary)", color: "#fff", border: "none", borderRadius: "8px", cursor: "pointer", fontFamily: "inherit", fontWeight: 500, display: "flex", alignItems: "center", gap: "6px", transition: "opacity 0.15s" }}
                onMouseEnter={e => (e.currentTarget.style.opacity = "0.85")}
                onMouseLeave={e => (e.currentTarget.style.opacity = "1")}
              >
                <svg width="11" height="11" viewBox="0 0 11 11" fill="none">
                  <path d="M1 5.5A4.5 4.5 0 109 2.5M9 1v2H7" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                Retry
              </button>
            )}
          </div>
        </div>

        {/* ── Activity log ── */}
        <div style={{ marginBottom: "24px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "8px" }}>
            <span style={{ fontSize: "11px", fontWeight: 500, color: "var(--text-muted)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
              Activity
            </span>
            {isRunning && (
              <span style={{ display: "flex", gap: "3px", alignItems: "center" }}>
                {[0, 1, 2].map(i => (
                  <span key={i} style={{ width: "3px", height: "3px", borderRadius: "50%", background: "#c9f135", animation: `bounce 1.2s ease-in-out ${i * 0.2}s infinite` }} />
                ))}
              </span>
            )}
          </div>
          <LiveStatusFeed jobId={id} jobStatus={job.status} />
          {job.error && (
            <div style={{ marginTop: "8px", padding: "10px 14px", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: "8px", fontSize: "12.5px", color: "#dc2626", fontFamily: "var(--font-geist-mono), monospace" }}>
              {job.error}
            </div>
          )}
        </div>

        {/* ── Diff badges ── */}
        {result?.diff && (result.diff.added > 0 || result.diff.removed > 0 || (result.diff.changed ?? 0) > 0) && (
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "16px", padding: "10px 14px", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "10px" }}>
            <span style={{ fontSize: "11px", fontWeight: 500, color: "var(--text-muted)", letterSpacing: "0.06em", textTransform: "uppercase", marginRight: "4px" }}>Changes</span>
            {result.diff.added > 0 && <DiffPill type="added" n={result.diff.added} />}
            {result.diff.changed > 0 && <DiffPill type="changed" n={result.diff.changed} />}
            {result.diff.removed > 0 && <DiffPill type="removed" n={result.diff.removed} />}
          </div>
        )}

        {/* ── Results ── */}
        {result && result.structured_data.length > 0 && (
          <div>
            {/* Results header */}
            <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "12px" }}>
              <span style={{ fontSize: "11px", fontWeight: 500, color: "var(--text-muted)", letterSpacing: "0.08em", textTransform: "uppercase", flex: 1 }}>
                {result.row_count} {result.row_count === 1 ? "record" : "records"}
              </span>
              <ExportPill resultId={result.id} format="json" label="JSON" />
              <ExportPill resultId={result.id} format="csv" label="CSV" accent />
            </div>
            <ResultsTable
              data={result.structured_data as Record<string, unknown>[]}
              schema={result.schema_detected ?? []}
              diff={result.diff}
            />
          </div>
        )}
      </div>

      <style>{`
        @keyframes statusPulse {
          0%   { box-shadow: 0 0 0 0 ${dotColor}60; }
          70%  { box-shadow: 0 0 0 6px ${dotColor}00; }
          100% { box-shadow: 0 0 0 0 ${dotColor}00; }
        }
      `}</style>
    </div>
  );
}

function StatChip({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div style={{ display: "flex", alignItems: "baseline", gap: "4px" }}>
      <span style={{ fontSize: "13px", fontWeight: accent ? 600 : 400, color: accent ? "var(--text-primary)" : "var(--text-secondary)" }}>
        {value}
      </span>
      <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>{label}</span>
    </div>
  );
}

function DiffPill({ type, n }: { type: "added" | "changed" | "removed"; n: number }) {
  const cfg = {
    added:   { bg: "#f0fdf4", color: "#15803d", border: "#bbf7d0", prefix: "+" },
    changed: { bg: "#fefce8", color: "#854d0e", border: "#fef08a", prefix: "~" },
    removed: { bg: "#fef2f2", color: "#b91c1c", border: "#fecaca", prefix: "−" },
  }[type];
  return (
    <span style={{ padding: "2px 8px", borderRadius: "5px", fontSize: "12px", fontWeight: 500, background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.border}`, fontFamily: "var(--font-geist-mono), monospace" }}>
      {cfg.prefix}{n}
    </span>
  );
}

function ExportPill({ resultId, format, label, accent }: { resultId: string; format: "json" | "csv"; label: string; accent?: boolean }) {
  return (
    <button
      onClick={() => window.open(getExportUrl(resultId, format), "_blank")}
      style={{
        padding: "5px 12px", fontSize: "12px", fontWeight: 500,
        border: `1px solid ${accent ? "var(--text-primary)" : "var(--border)"}`,
        borderRadius: "7px",
        background: accent ? "var(--text-primary)" : "transparent",
        color: accent ? "#fff" : "var(--text-secondary)",
        cursor: "pointer", fontFamily: "inherit", transition: "opacity 0.12s",
        display: "flex", alignItems: "center", gap: "5px",
      }}
      onMouseEnter={e => (e.currentTarget.style.opacity = "0.75")}
      onMouseLeave={e => (e.currentTarget.style.opacity = "1")}
    >
      <svg width="11" height="11" viewBox="0 0 11 11" fill="none">
        <path d="M5.5 1v6M2.5 8l3 2.5L8.5 8M1 9.5h9" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      {label}
    </button>
  );
}
