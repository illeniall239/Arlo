import type { JobStatus } from "@/types";

const config: Record<JobStatus, { label: string; dot: string }> = {
  pending:     { label: "Pending",     dot: "#b4b4ae" },
  planning:    { label: "Planning",    dot: "#60a5fa" },
  running:     { label: "Running",     dot: "#f59e0b" },
  structuring: { label: "Structuring", dot: "#a78bfa" },
  completed:   { label: "Done",        dot: "#34d399" },
  failed:      { label: "Failed",      dot: "#f87171" },
  cancelled:   { label: "Cancelled",   dot: "#b4b4ae" },
};

export default function JobStatusBadge({ status }: { status: JobStatus }) {
  const { label, dot } = config[status] ?? config.pending;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "5px" }}>
      <span style={{
        width: "6px", height: "6px", borderRadius: "50%",
        background: dot, flexShrink: 0,
        boxShadow: status === "running" || status === "planning" || status === "structuring"
          ? `0 0 0 2px ${dot}30` : "none",
      }} />
      <span style={{ fontSize: "12px", color: "var(--text-secondary)", fontWeight: 400 }}>
        {label}
      </span>
    </span>
  );
}
