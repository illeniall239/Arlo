"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const PAGE_SIZE = 20;

interface Job {
  id: string;
  url: string;
  prompt: string;
  status: string;
  created_at: string;
}

const STATUS_COLOR: Record<string, { bg: string; text: string; border: string }> = {
  completed: { bg: "#f0fdf4", text: "#15803d", border: "#bbf7d0" },
  failed:    { bg: "#fef2f2", text: "#b91c1c", border: "#fecaca" },
  cancelled: { bg: "#f4f4f5", text: "#52525b", border: "#e4e4e7" },
  running:   { bg: "#eff6ff", text: "#1d4ed8", border: "#bfdbfe" },
  pending:   { bg: "#fffbeb", text: "#b45309", border: "#fde68a" },
};

function StatusBadge({ status }: { status: string }) {
  const c = STATUS_COLOR[status] ?? STATUS_COLOR.cancelled;
  return (
    <span style={{
      padding: "2px 9px", borderRadius: "20px", fontSize: "11.5px", fontWeight: 500,
      background: c.bg, color: c.text, border: `1px solid ${c.border}`,
      textTransform: "capitalize", whiteSpace: "nowrap",
    }}>
      {status}
    </span>
  );
}

export default function JobsPage() {
  const [jobs, setJobs]       = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage]       = useState(1);
  const [total, setTotal]     = useState(0);

  useEffect(() => {
    setLoading(true);
    fetch(`${API_BASE}/jobs/?page_size=${PAGE_SIZE}&page=${page}`)
      .then((r) => r.json())
      .then((data) => {
        setJobs(data.data ?? []);
        setTotal(data.meta?.total ?? 0);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [page]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="page-pad" style={{ padding: "28px 32px" }}>
      <div style={{ marginBottom: "24px" }}>
        <h1 style={{ fontSize: "20px", fontWeight: 650, color: "var(--text-primary)", letterSpacing: "-0.02em", marginBottom: "4px" }}>
          All jobs
        </h1>
        <p style={{ fontSize: "13.5px", color: "var(--text-secondary)" }}>
          {total > 0 ? `${total} job${total === 1 ? "" : "s"} total` : "No jobs yet."}
        </p>
      </div>

      <div style={{ overflowX: "auto", WebkitOverflowScrolling: "touch" }}>
      <div style={{ border: "1px solid var(--border)", borderRadius: "10px", overflow: "hidden", background: "var(--surface)" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", minWidth: "540px" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border)", background: "var(--page-bg)" }}>
              {["URL", "Goal", "Status", "Date", ""].map((h) => (
                <th key={h} style={{
                  padding: "9px 16px", textAlign: "left",
                  fontSize: "11px", fontWeight: 500, color: "var(--text-muted)",
                  letterSpacing: "0.06em", textTransform: "uppercase",
                }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={6} style={{ padding: "32px", textAlign: "center", fontSize: "13.5px", color: "var(--text-muted)" }}>
                  Loading…
                </td>
              </tr>
            )}
            {!loading && jobs.length === 0 && (
              <tr>
                <td colSpan={6} style={{ padding: "48px", textAlign: "center", fontSize: "13.5px", color: "var(--text-muted)" }}>
                  No jobs found. Run your first scrape from the dashboard.
                </td>
              </tr>
            )}
            {jobs.map((job) => {
              let hostname = job.url;
              try { hostname = new URL(job.url).hostname.replace(/^www\./, ""); } catch {}
              return (
                <tr
                  key={job.id}
                  style={{ borderBottom: "1px solid var(--border)", transition: "background 0.1s" }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "var(--page-bg)")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                >
                  <td style={{ padding: "12px 16px", maxWidth: "180px" }}>
                    <span style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: "13px", color: "var(--text-secondary)" }}>
                      {hostname}
                    </span>
                  </td>
                  <td style={{ padding: "12px 16px", maxWidth: "300px" }}>
                    <Link href={`/jobs/${job.id}`} style={{ textDecoration: "none" }}>
                      <span style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: "13.5px", color: "var(--text-primary)", fontWeight: 450 }}>
                        {job.prompt}
                      </span>
                    </Link>
                  </td>
                  <td style={{ padding: "12px 16px" }}>
                    <StatusBadge status={job.status} />
                  </td>
                  <td style={{ padding: "12px 16px", fontSize: "13px", color: "var(--text-muted)", whiteSpace: "nowrap" }}>
                    {new Date(job.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                  </td>
                  <td style={{ padding: "12px 16px" }}>
                    <Link href={`/jobs/${job.id}`} style={{ fontSize: "12.5px", color: "var(--text-secondary)", textDecoration: "none", fontWeight: 500 }}>
                      Open →
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      </div>

      {totalPages > 1 && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "8px", marginTop: "16px" }}>
          <button
            onClick={() => setPage(Math.max(1, page - 1))}
            disabled={page === 1}
            style={{ padding: "6px 12px", fontSize: "12.5px", border: "1px solid var(--border)", borderRadius: "7px", background: "var(--surface)", color: "var(--text-secondary)", cursor: page === 1 ? "not-allowed" : "pointer", opacity: page === 1 ? 0.4 : 1, fontFamily: "inherit" }}
          >
            ← Prev
          </button>
          <span style={{ fontSize: "12.5px", color: "var(--text-muted)" }}>{page} / {totalPages}</span>
          <button
            onClick={() => setPage(Math.min(totalPages, page + 1))}
            disabled={page === totalPages}
            style={{ padding: "6px 12px", fontSize: "12.5px", border: "1px solid var(--border)", borderRadius: "7px", background: "var(--surface)", color: "var(--text-secondary)", cursor: page === totalPages ? "not-allowed" : "pointer", opacity: page === totalPages ? 0.4 : 1, fontFamily: "inherit" }}
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}
