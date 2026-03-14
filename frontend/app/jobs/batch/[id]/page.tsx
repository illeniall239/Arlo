"use client";

import { use, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { fetchBatch } from "@/lib/api";
import type { JobSummary } from "@/types";

const TERMINAL = new Set(["completed", "failed", "cancelled"]);

const STATUS_COLOR: Record<string, { bg: string; text: string; border: string }> = {
  completed:   { bg: "#f0fdf4", text: "#15803d", border: "#bbf7d0" },
  failed:      { bg: "#fef2f2", text: "#b91c1c", border: "#fecaca" },
  cancelled:   { bg: "#f4f4f5", text: "#52525b", border: "#e4e4e7" },
  running:     { bg: "#eff6ff", text: "#1d4ed8", border: "#bfdbfe" },
  planning:    { bg: "#eff6ff", text: "#1d4ed8", border: "#bfdbfe" },
  structuring: { bg: "#f5f3ff", text: "#6d28d9", border: "#ddd6fe" },
  pending:     { bg: "#fffbeb", text: "#b45309", border: "#fde68a" },
};

function StatusBadge({ status }: { status: string }) {
  const c = STATUS_COLOR[status] ?? STATUS_COLOR.cancelled;
  return (
    <span style={{
      padding: "2px 9px", borderRadius: "20px", fontSize: "11.5px", fontWeight: 500,
      background: c.bg, color: c.text, border: `1px solid ${c.border}`,
      textTransform: "capitalize", whiteSpace: "nowrap", flexShrink: 0,
    }}>
      {status}
    </span>
  );
}

export default function BatchPage({ params }: { params: Promise<{ id: string }> }) {
  const { id }  = use(params);
  const [jobs, setJobs]     = useState<JobSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = async () => {
    try {
      const data = await fetchBatch(id);
      setJobs(data.jobs);
      setLoading(false);
      if (data.jobs.length > 0 && data.jobs.every((j) => TERMINAL.has(j.status))) {
        if (intervalRef.current) clearInterval(intervalRef.current);
      }
    } catch {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    intervalRef.current = setInterval(load, 3000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [id]);

  const done      = jobs.filter((j) => TERMINAL.has(j.status)).length;
  const completed = jobs.filter((j) => j.status === "completed").length;
  const failed    = jobs.filter((j) => j.status === "failed").length;
  const pct       = jobs.length ? Math.round((done / jobs.length) * 100) : 0;

  if (loading) {
    return (
      <div style={{ padding: "28px 32px" }}>
        <p style={{ fontSize: "13.5px", color: "var(--text-muted)" }}>Loading…</p>
      </div>
    );
  }

  return (
    <div style={{ padding: "28px 32px" }}>

      {/* Header */}
      <div style={{ marginBottom: "20px" }}>
        <h1 style={{ fontSize: "20px", fontWeight: 650, color: "var(--text-primary)", letterSpacing: "-0.02em", marginBottom: "8px" }}>
          Batch job
        </h1>
        <div style={{ display: "flex", gap: "16px", fontSize: "13.5px", color: "var(--text-secondary)", alignItems: "center" }}>
          <span>{done}/{jobs.length} done</span>
          {completed > 0 && <span style={{ color: "#15803d", fontWeight: 500 }}>{completed} completed</span>}
          {failed > 0 && <span style={{ color: "#b91c1c", fontWeight: 500 }}>{failed} failed</span>}
        </div>
      </div>

      {/* Progress bar */}
      <div style={{ marginBottom: "24px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
          <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>Progress</span>
          <span style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 500 }}>{pct}%</span>
        </div>
        <div style={{ height: "6px", background: "var(--border)", borderRadius: "3px", overflow: "hidden" }}>
          <div style={{
            height: "100%",
            width: `${pct}%`,
            background: failed > 0 ? "#f59e0b" : "#1c1c1a",
            transition: "width 0.4s ease",
            borderRadius: "3px",
          }} />
        </div>
      </div>

      {/* Job list */}
      <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
        {jobs.map((job, i) => (
          <div
            key={job.id}
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "10px",
              padding: "13px 16px",
              display: "flex",
              alignItems: "center",
              gap: "12px",
            }}
          >
            <span style={{ fontSize: "11.5px", color: "var(--text-muted)", minWidth: "22px", fontWeight: 500 }}>
              {i + 1}
            </span>
            <StatusBadge status={job.status} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <a
                href={job.url}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  fontSize: "13px", color: "var(--text-primary)", textDecoration: "none",
                  display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                }}
                onMouseEnter={(e) => (e.currentTarget.style.color = "var(--text-secondary)")}
                onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-primary)")}
              >
                {job.url}
              </a>
              {job.completed_at && job.started_at && (
                <span style={{ fontSize: "11.5px", color: "var(--text-muted)" }}>
                  {Math.round((new Date(job.completed_at).getTime() - new Date(job.started_at).getTime()) / 1000)}s
                </span>
              )}
            </div>
            {TERMINAL.has(job.status) && (
              <Link
                href={`/jobs/${job.id}`}
                style={{ fontSize: "12.5px", color: "var(--text-secondary)", textDecoration: "none", flexShrink: 0, fontWeight: 500 }}
              >
                View →
              </Link>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
