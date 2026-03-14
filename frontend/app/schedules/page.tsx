"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { createSchedule, deleteSchedule, fetchSchedules, updateSchedule } from "@/lib/api";
import type { Schedule } from "@/types";

const INTERVALS = [
  { label: "Hourly",  value: 60    },
  { label: "Daily",   value: 1440  },
  { label: "Weekly",  value: 10080 },
];

const inputStyle: React.CSSProperties = {
  width: "100%",
  border: "1px solid var(--border)",
  borderRadius: "8px",
  padding: "8px 12px",
  fontSize: "13.5px",
  color: "var(--text-primary)",
  background: "var(--surface)",
  outline: "none",
  fontFamily: "inherit",
  transition: "border-color 0.15s",
};

const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: "12px",
  fontWeight: 500,
  color: "var(--text-secondary)",
  marginBottom: "6px",
};

const STATUS_COLOR: Record<string, string> = {
  completed: "#15803d",
  failed:    "#b91c1c",
  cancelled: "#6b7280",
  running:   "#1d4ed8",
  pending:   "#b45309",
};

export default function SchedulesPage() {
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [loading, setLoading]     = useState(true);
  const [showForm, setShowForm]   = useState(false);

  const [url, setUrl]         = useState("");
  const [prompt, setPrompt]   = useState("");
  const [interval, setInterval] = useState(1440);
  const [maxPages, setMaxPages] = useState(5);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError]   = useState<string | null>(null);

  async function load() {
    try { setSchedules(await fetchSchedules()); } catch { /* ignore */ }
    setLoading(false);
  }

  useEffect(() => { load(); }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setFormError(null);
    try {
      await createSchedule({ url, prompt, interval_minutes: interval, max_pages: maxPages });
      setUrl(""); setPrompt(""); setInterval(1440); setMaxPages(5);
      setShowForm(false);
      await load();
    } catch (err: unknown) {
      const e = err as { body?: { detail?: string }; message?: string };
      setFormError(e.body?.detail ?? e.message ?? "Failed to create schedule");
    }
    setSubmitting(false);
  }

  async function handleToggle(s: Schedule) {
    await updateSchedule(s.id, { enabled: !s.enabled });
    await load();
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this schedule?")) return;
    await deleteSchedule(id);
    await load();
  }

  return (
    <div style={{ padding: "28px 32px" }}>

      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "28px" }}>
        <div>
          <h1 style={{ fontSize: "20px", fontWeight: 650, color: "var(--text-primary)", letterSpacing: "-0.02em", marginBottom: "4px" }}>
            Schedules
          </h1>
          <p style={{ fontSize: "13.5px", color: "var(--text-secondary)" }}>
            Automatically re-run a scrape on a schedule. Each run diffs against the previous result.
          </p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          style={{
            padding: "8px 16px", fontSize: "13.5px", fontWeight: 500,
            background: showForm ? "transparent" : "var(--text-primary)",
            color: showForm ? "var(--text-secondary)" : "#fff",
            border: showForm ? "1px solid var(--border)" : "none",
            borderRadius: "8px", cursor: "pointer", flexShrink: 0, marginLeft: "16px",
            transition: "background 0.15s",
          }}
        >
          {showForm ? "Cancel" : "+ New schedule"}
        </button>
      </div>

      {/* Create form */}
      {showForm && (
        <form
          onSubmit={handleCreate}
          style={{
            background: "var(--surface)", border: "1px solid var(--border)",
            borderRadius: "10px", padding: "20px 22px", marginBottom: "20px",
          }}
        >
          <div style={{ fontSize: "13.5px", fontWeight: 600, color: "var(--text-primary)", marginBottom: "16px", letterSpacing: "-0.01em" }}>
            New schedule
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
            <div>
              <label style={labelStyle}>URL to scrape</label>
              <input
                type="url" required value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://example.com/listings"
                style={inputStyle}
                onFocus={(e) => (e.currentTarget.style.borderColor = "var(--border-strong)")}
                onBlur={(e) => (e.currentTarget.style.borderColor = "var(--border)")}
              />
            </div>
            <div>
              <label style={labelStyle}>What to extract</label>
              <textarea
                required minLength={5} value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder='e.g. "Get all product names, prices, and URLs"'
                rows={2}
                style={{ ...inputStyle, resize: "none", lineHeight: 1.5 }}
                onFocus={(e) => (e.currentTarget.style.borderColor = "var(--border-strong)")}
                onBlur={(e) => (e.currentTarget.style.borderColor = "var(--border)")}
              />
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto", gap: "12px", alignItems: "flex-end" }}>
              <div>
                <label style={labelStyle}>Run every</label>
                <select
                  value={interval}
                  onChange={(e) => setInterval(Number(e.target.value))}
                  style={{ ...inputStyle, cursor: "pointer" }}
                >
                  {INTERVALS.map((i) => (
                    <option key={i.value} value={i.value}>{i.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label style={labelStyle}>Max pages</label>
                <input
                  type="number" min={1} max={50} value={maxPages}
                  onChange={(e) => setMaxPages(Math.max(1, Math.min(50, Number(e.target.value))))}
                  style={inputStyle}
                  onFocus={(e) => (e.currentTarget.style.borderColor = "var(--border-strong)")}
                  onBlur={(e) => (e.currentTarget.style.borderColor = "var(--border)")}
                />
              </div>
              <button
                type="submit" disabled={submitting}
                style={{
                  padding: "8px 20px", fontSize: "13.5px", fontWeight: 500,
                  background: submitting ? "var(--border-strong)" : "var(--text-primary)",
                  color: "#fff", border: "none", borderRadius: "8px",
                  cursor: submitting ? "not-allowed" : "pointer", fontFamily: "inherit",
                  whiteSpace: "nowrap",
                }}
              >
                {submitting ? "Creating…" : "Create"}
              </button>
            </div>
            {formError && (
              <p style={{ fontSize: "12.5px", color: "#b91c1c", margin: 0 }}>{formError}</p>
            )}
          </div>
        </form>
      )}

      {/* List */}
      {loading ? (
        <p style={{ fontSize: "13.5px", color: "var(--text-muted)" }}>Loading…</p>
      ) : schedules.length === 0 ? (
        <div style={{
          padding: "56px 32px", textAlign: "center",
          border: "1px dashed var(--border)", borderRadius: "10px",
          color: "var(--text-muted)", fontSize: "13.5px",
        }}>
          No schedules yet — create one above.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          {schedules.map((s) => (
            <div
              key={s.id}
              style={{
                background: "var(--surface)", border: "1px solid var(--border)",
                borderRadius: "10px", padding: "16px 20px",
                opacity: s.enabled ? 1 : 0.55,
                transition: "opacity 0.15s",
              }}
            >
              <div style={{ display: "flex", alignItems: "flex-start", gap: "14px" }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: "13.5px", fontWeight: 500, color: "var(--text-primary)", marginBottom: "3px" }}>
                    {s.prompt}
                  </div>
                  <a
                    href={s.url} target="_blank" rel="noopener noreferrer"
                    style={{ fontSize: "12px", color: "var(--text-muted)", textDecoration: "none", wordBreak: "break-all" }}
                    onMouseEnter={(e) => (e.currentTarget.style.color = "var(--text-secondary)")}
                    onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-muted)")}
                  >
                    {s.url}
                  </a>
                  <div style={{ display: "flex", gap: "14px", marginTop: "8px", flexWrap: "wrap", alignItems: "center" }}>
                    <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>
                      {INTERVALS.find((i) => i.value === s.interval_minutes)?.label ?? `Every ${s.interval_minutes}min`}
                    </span>
                    {s.next_run_at && (
                      <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>
                        Next: {new Date(s.next_run_at).toLocaleString()}
                      </span>
                    )}
                    {s.last_status && (
                      <span style={{ fontSize: "12px", color: STATUS_COLOR[s.last_status] ?? "#6b7280", fontWeight: 500 }}>
                        {s.last_status}
                      </span>
                    )}
                    {s.last_job_id && (
                      <Link
                        href={`/jobs/${s.last_job_id}`}
                        style={{ fontSize: "12px", color: "var(--text-secondary)", textDecoration: "none" }}
                      >
                        Last run →
                      </Link>
                    )}
                  </div>
                </div>
                <div style={{ display: "flex", gap: "6px", flexShrink: 0 }}>
                  <button
                    onClick={() => handleToggle(s)}
                    style={{
                      padding: "5px 12px", fontSize: "12.5px",
                      border: "1px solid var(--border)", borderRadius: "7px",
                      background: "transparent", color: "var(--text-secondary)", cursor: "pointer",
                      fontFamily: "inherit", transition: "border-color 0.12s",
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.borderColor = "var(--border-strong)")}
                    onMouseLeave={(e) => (e.currentTarget.style.borderColor = "var(--border)")}
                  >
                    {s.enabled ? "Pause" : "Resume"}
                  </button>
                  <button
                    onClick={() => handleDelete(s.id)}
                    style={{
                      padding: "5px 12px", fontSize: "12.5px",
                      border: "1px solid #fecaca", borderRadius: "7px",
                      background: "transparent", color: "#b91c1c", cursor: "pointer",
                      fontFamily: "inherit",
                    }}
                  >
                    Delete
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
