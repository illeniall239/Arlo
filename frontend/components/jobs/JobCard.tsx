import Link from "next/link";
import type { JobSummary } from "@/types";
import JobStatusBadge from "./JobStatusBadge";

export default function JobCard({ job }: { job: JobSummary }) {
  const duration =
    job.completed_at && job.started_at
      ? Math.round(
          (new Date(job.completed_at).getTime() - new Date(job.started_at).getTime()) / 1000
        )
      : null;

  return (
    <Link href={`/jobs/${job.id}`} style={{ textDecoration: "none", display: "block" }}>
      <div style={{
        borderBottom: "1px solid var(--border)",
        padding: "14px 0",
        display: "flex",
        alignItems: "baseline",
        gap: "16px",
        cursor: "pointer",
        transition: "opacity 0.1s",
      }}
        onMouseEnter={e => (e.currentTarget.style.opacity = "0.7")}
        onMouseLeave={e => (e.currentTarget.style.opacity = "1")}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{
            fontSize: "13.5px",
            color: "var(--text-primary)",
            fontWeight: 450,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            marginBottom: "3px",
          }}>
            {job.prompt}
          </p>
          <p style={{ fontSize: "12px", color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {job.url}
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "12px", flexShrink: 0 }}>
          <JobStatusBadge status={job.status} />
          <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>
            {duration !== null ? `${duration}s` : new Date(job.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          </span>
        </div>
      </div>
    </Link>
  );
}
