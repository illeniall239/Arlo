"use client";

import React, { useEffect, useRef, useState } from "react";
import { agentStreamUrl, cancelAgentRun, fetchAgentRun } from "@/lib/api";
import type { AgentRunDetail, AgentSSEEvent } from "@/types";

interface Props {
  runId: string;
  goal: string;
  /** Called when this run reaches a terminal state, with the formatted response */
  onComplete?: (status: string, response?: string) => void;
  /** If true, show a cancel button (only relevant for the active turn) */
  showCancel?: boolean;
}

interface LogLine {
  id: number;
  type: AgentSSEEvent["type"];
  message: string;
}

const STATUS_COLOR: Record<string, { bg: string; text: string; border: string }> = {
  completed: { bg: "#f0fdf4", text: "#15803d", border: "#bbf7d0" },
  failed:    { bg: "#fef2f2", text: "#b91c1c", border: "#fecaca" },
  cancelled: { bg: "#f4f4f5", text: "#52525b", border: "#e4e4e7" },
};

// ── Avatar ─────────────────────────────────────────────────────────────────────

function AgentAvatar() {
  return (
    <div style={{
      width: "30px", height: "30px", borderRadius: "50%",
      background: "#1c1c1a", display: "flex", alignItems: "center",
      justifyContent: "center", flexShrink: 0, marginTop: "2px",
    }}>
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
        <rect x="2" y="2" width="5" height="5" rx="1" fill="white" />
        <rect x="9" y="2" width="5" height="5" rx="1" fill="white" />
        <rect x="2" y="9" width="5" height="5" rx="1" fill="white" />
        <rect x="9" y="9" width="5" height="5" rx="1" fill="#c9f135" />
      </svg>
    </div>
  );
}

// ── Thinking section ───────────────────────────────────────────────────────────

function ThinkingSection({ lines, isActive }: { lines: LogLine[]; isActive: boolean }) {
  const [open, setOpen] = useState(true);
  const latestMessage = lines[lines.length - 1]?.message ?? "";

  return (
    <div style={{ marginBottom: "12px" }}>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{ display: "flex", alignItems: "center", gap: "6px", background: "none", border: "none", cursor: "pointer", padding: "0", marginBottom: open ? "8px" : "0" }}
      >
        {isActive ? (
          <span style={{ display: "flex", gap: "3px", alignItems: "center" }}>
            {[0, 1, 2].map((i) => (
              <span key={i} style={{
                width: "5px", height: "5px", borderRadius: "50%",
                background: "#94a3b8", display: "inline-block",
                animation: `bounce 1.2s ease-in-out ${i * 0.2}s infinite`,
              }} />
            ))}
          </span>
        ) : (
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none"
            style={{ transform: open ? "rotate(90deg)" : "rotate(0deg)", transition: "transform 0.15s", flexShrink: 0 }}>
            <path d="M4 2l4 4-4 4" stroke="#94a3b8" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
        <span style={{ fontSize: "12.5px", color: "#94a3b8" }}>
          {isActive ? (latestMessage || "Thinking…") : `Reasoning · ${lines.length} steps`}
        </span>
      </button>

      {open && !isActive && (
        <div style={{ borderLeft: "2px solid var(--border)", paddingLeft: "12px", display: "flex", flexDirection: "column", gap: "3px" }}>
          {lines.map((line) => (
            <div key={line.id} style={{
              fontSize: "12px",
              color: line.type === "status" ? "#60a5fa" : line.type === "done" ? "#4ade80" : line.type === "error" ? "#f87171" : "#94a3b8",
              lineHeight: 1.6,
            }}>
              {line.message}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function AgentTrace({ runId, goal, onComplete, showCancel }: Props) {
  const [lines, setLines]       = useState<LogLine[]>([]);
  const [status, setStatus]     = useState<string>("pending");
  const [run, setRun]           = useState<AgentRunDetail | null>(null);
  const [resultRows, setResultRows] = useState<Record<string, unknown>[]>([]);
  const [search, setSearch]     = useState("");
  const [cancelling, setCancelling] = useState(false);
  const counter  = useRef(0);
  const notified = useRef(false);

  useEffect(() => {
    let es: EventSource | null = null;
    let isActive = true;

    fetchAgentRun(runId).then((detail) => {
      if (!isActive) return;
      const terminal = ["completed", "failed", "cancelled"];
      if (terminal.includes(detail.status)) {
        setStatus(detail.status);
        setRun(detail);
        if (detail.result) {
          try { setResultRows(JSON.parse(detail.result)); } catch { /* ignore */ }
        }
        return;
      }

      es = new EventSource(agentStreamUrl(runId));
      es.onmessage = (e) => {
        const event: AgentSSEEvent = JSON.parse(e.data);
        const text = event.message ?? event.detail ??
          (event.type === "done" ? `Done — ${event.rows} records. ${event.summary ?? ""}` : event.type);

        setLines((prev) => [...prev, { id: counter.current++, type: event.type, message: text }]);

        if (event.type === "done") {
          setStatus("completed");
          es?.close();
          fetchAgentRun(runId).then((d) => {
            if (!isActive) return;
            setRun(d);
            if (d.result) {
              try { setResultRows(JSON.parse(d.result)); } catch { /* ignore */ }
            }
          });
        } else if (event.type === "error") {
          setStatus("failed");
          es?.close();
        } else {
          setStatus("running");
        }
      };

      es.onerror = () => {
        setStatus((s) => (s === "running" || s === "pending") ? "failed" : s);
        es?.close();
      };
    }).catch(() => { if (isActive) setStatus("failed"); });

    return () => { isActive = false; es?.close(); };
  }, [runId]);

  // Notify parent once when terminal, passing back the formatted response
  useEffect(() => {
    if (!notified.current && ["completed", "failed", "cancelled"].includes(status)) {
      notified.current = true;
      onComplete?.(status, run?.formatted_response ?? undefined);
    }
  }, [status, run, onComplete]);

  async function handleCancel() {
    setCancelling(true);
    try { await cancelAgentRun(runId); } catch { /* ignore */ }
    setCancelling(false);
  }

  const isRunning   = status === "pending" || status === "running";
  const isTerminal  = ["completed", "failed", "cancelled"].includes(status);
  const filteredRows = search
    ? resultRows.filter((r) => JSON.stringify(r).toLowerCase().includes(search.toLowerCase()))
    : resultRows;
  const columns = resultRows.length > 0 ? Object.keys(resultRows[0]) : [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0" }}>

      {/* User message — right */}
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "24px" }}>
        <div style={{
          background: "#1c1c1a", color: "#ffffff",
          padding: "12px 16px", borderRadius: "18px 18px 4px 18px",
          fontSize: "14px", lineHeight: 1.6, maxWidth: "65%", wordBreak: "break-word",
        }}>
          {goal}
        </div>
      </div>

      {/* Agent response — left */}
      <div style={{ display: "flex", gap: "12px", alignItems: "flex-start" }}>
        <AgentAvatar />
        <div style={{ flex: 1, minWidth: 0 }}>

          {/* Thinking */}
          {(lines.length > 0 || isRunning) && (
            <ThinkingSection lines={lines} isActive={isRunning} />
          )}
          {isRunning && lines.length === 0 && (
            <div style={{ fontSize: "13.5px", color: "var(--text-muted)", marginBottom: "12px" }}>Starting up…</div>
          )}

          {/* Cancel button */}
          {isRunning && showCancel && (
            <button
              onClick={handleCancel} disabled={cancelling}
              style={{
                marginBottom: "12px", padding: "3px 10px", fontSize: "12px",
                background: "none", border: "1px solid var(--border)",
                borderRadius: "5px", cursor: "pointer", color: "var(--text-secondary)",
              }}
            >
              {cancelling ? "Cancelling…" : "Cancel"}
            </button>
          )}

          {/* Final response */}
          {run?.formatted_response && (
            <div style={{ fontSize: "14px", lineHeight: 1.7, color: "var(--text-primary)" }}>
              <MarkdownView md={run.formatted_response} />
            </div>
          )}

          {/* Status badge — only on terminal, non-completed */}
          {isTerminal && status !== "completed" && (
            <span style={{
              display: "inline-block", padding: "2px 10px", borderRadius: "20px",
              fontSize: "11.5px", fontWeight: 500,
              background: (STATUS_COLOR[status]?.bg ?? "#f4f4f5"),
              color: (STATUS_COLOR[status]?.text ?? "#52525b"),
              border: `1px solid ${STATUS_COLOR[status]?.border ?? "#e4e4e7"}`,
              textTransform: "capitalize",
            }}>
              {status}
            </span>
          )}

          {/* Data table */}
          {status === "completed" && resultRows.length > 0 && (
            <div style={{ marginTop: "20px" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "10px", flexWrap: "wrap", gap: "8px" }}>
                <span style={{ fontSize: "12.5px", color: "var(--text-muted)" }}>{resultRows.length} records found</span>
                <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
                  <input
                    value={search} onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search…"
                    style={{
                      padding: "4px 9px", fontSize: "12.5px",
                      border: "1px solid var(--border)", borderRadius: "6px",
                      background: "var(--surface)", color: "var(--text-primary)",
                      outline: "none", width: "140px",
                    }}
                  />
                  <ExportButtons data={resultRows} />
                </div>
              </div>
              <div style={{ overflowX: "auto", border: "1px solid var(--border)", borderRadius: "8px" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12.5px" }}>
                  <thead>
                    <tr style={{ background: "var(--surface)", borderBottom: "1px solid var(--border)" }}>
                      {columns.map((col) => (
                        <th key={col} style={{ padding: "8px 12px", textAlign: "left", color: "var(--text-secondary)", fontWeight: 500, whiteSpace: "nowrap" }}>
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filteredRows.slice(0, 200).map((row, i) => (
                      <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                        {columns.map((col) => (
                          <td key={col} style={{ padding: "7px 12px", color: "var(--text-primary)", maxWidth: "280px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {String(row[col] ?? "")}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {filteredRows.length > 200 && (
                <div style={{ fontSize: "12px", color: "var(--text-muted)", marginTop: "6px" }}>
                  Showing first 200 of {filteredRows.length} rows
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Markdown renderer ──────────────────────────────────────────────────────────

function MarkdownView({ md }: { md: string }) {
  return <div>{parseMarkdown(md).map((b, i) => renderBlock(b, i))}</div>;
}

type MdNode =
  | { kind: "h2"; text: string } | { kind: "h3"; text: string }
  | { kind: "table"; header: string[]; rows: string[][] }
  | { kind: "ul"; items: string[] } | { kind: "ol"; items: string[] }
  | { kind: "p"; text: string } | { kind: "hr" };

function parseMarkdown(md: string): MdNode[] {
  const lines = md.split("\n");
  const blocks: MdNode[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (/^---+$/.test(line.trim())) { blocks.push({ kind: "hr" }); i++; continue; }
    if (line.startsWith("## ")) { blocks.push({ kind: "h2", text: line.slice(3).trim() }); i++; continue; }
    if (line.startsWith("### ")) { blocks.push({ kind: "h3", text: line.slice(4).trim() }); i++; continue; }
    if (line.startsWith("|")) {
      const tl: string[] = [];
      while (i < lines.length && lines[i].startsWith("|")) { tl.push(lines[i]); i++; }
      const pr = (l: string) => l.split("|").slice(1, -1).map((c) => c.trim());
      blocks.push({ kind: "table", header: pr(tl[0]), rows: tl.slice(2).map(pr) });
      continue;
    }
    if (/^[-*] /.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*] /.test(lines[i])) { items.push(lines[i].replace(/^[-*] /, "")); i++; }
      blocks.push({ kind: "ul", items }); continue;
    }
    if (/^\d+\. /.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\. /.test(lines[i])) { items.push(lines[i].replace(/^\d+\. /, "")); i++; }
      blocks.push({ kind: "ol", items }); continue;
    }
    if (line.trim() === "") { i++; continue; }
    const pl: string[] = [];
    while (i < lines.length && lines[i].trim() !== "" && !lines[i].startsWith("#") && !lines[i].startsWith("|") && !/^[-*\d]/.test(lines[i])) {
      pl.push(lines[i]); i++;
    }
    if (pl.length) blocks.push({ kind: "p", text: pl.join(" ") });
  }
  return blocks;
}

function renderInline(text: string): React.ReactNode {
  const parts: React.ReactNode[] = [];
  let rest = text; let key = 0;
  while (rest.length) {
    const lm = rest.match(/\[([^\]]+)\]\(([^)]+)\)/);
    const bm = rest.match(/\*\*([^*]+)\*\*/);
    const li = lm ? rest.indexOf(lm[0]) : Infinity;
    const bi = bm ? rest.indexOf(bm[0]) : Infinity;
    if (lm && li <= bi) {
      parts.push(rest.slice(0, li));
      parts.push(<a key={key++} href={lm[2]} target="_blank" rel="noreferrer" style={{ color: "#3b82f6", textDecoration: "underline" }}>{lm[1]}</a>);
      rest = rest.slice(li + lm[0].length);
    } else if (bm && bi < Infinity) {
      parts.push(rest.slice(0, bi));
      parts.push(<strong key={key++}>{bm[1]}</strong>);
      rest = rest.slice(bi + bm[0].length);
    } else { parts.push(rest); break; }
  }
  return parts;
}

function renderBlock(block: MdNode, idx: number): React.ReactNode {
  switch (block.kind) {
    case "hr": return <hr key={idx} style={{ border: "none", borderTop: "1px solid var(--border)", margin: "20px 0" }} />;
    case "h2": return <h2 key={idx} style={{ fontSize: "17px", fontWeight: 650, margin: "24px 0 10px", color: "var(--text-primary)", letterSpacing: "-0.02em" }}>{renderInline(block.text)}</h2>;
    case "h3": return <h3 key={idx} style={{ fontSize: "15px", fontWeight: 600, margin: "18px 0 8px", color: "var(--text-primary)" }}>{renderInline(block.text)}</h3>;
    case "p":  return <p key={idx} style={{ margin: "0 0 14px", color: "var(--text-primary)", lineHeight: 1.75 }}>{renderInline(block.text)}</p>;
    case "ul": return <ul key={idx} style={{ margin: "0 0 14px", paddingLeft: "22px", color: "var(--text-primary)" }}>{block.items.map((it, i) => <li key={i} style={{ marginBottom: "5px", lineHeight: 1.65 }}>{renderInline(it)}</li>)}</ul>;
    case "ol": return <ol key={idx} style={{ margin: "0 0 14px", paddingLeft: "22px", color: "var(--text-primary)" }}>{block.items.map((it, i) => <li key={i} style={{ marginBottom: "5px", lineHeight: 1.65 }}>{renderInline(it)}</li>)}</ol>;
    case "table": return (
      <div key={idx} style={{ overflowX: "auto", marginBottom: "16px", border: "1px solid var(--border)", borderRadius: "8px" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
          <thead><tr style={{ background: "var(--surface)", borderBottom: "1px solid var(--border)" }}>
            {block.header.map((h, i) => <th key={i} style={{ padding: "8px 14px", textAlign: "left", color: "var(--text-secondary)", fontWeight: 500, whiteSpace: "nowrap" }}>{h}</th>)}
          </tr></thead>
          <tbody>{block.rows.map((row, ri) => (
            <tr key={ri} style={{ borderBottom: "1px solid var(--border)" }}>
              {row.map((cell, ci) => <td key={ci} style={{ padding: "7px 14px", color: "var(--text-primary)" }}>{renderInline(cell)}</td>)}
            </tr>
          ))}</tbody>
        </table>
      </div>
    );
  }
}

// ── Export buttons ─────────────────────────────────────────────────────────────

const btnStyle: React.CSSProperties = {
  padding: "4px 10px", fontSize: "12px", background: "none",
  border: "1px solid var(--border)", borderRadius: "5px",
  cursor: "pointer", color: "var(--text-secondary)",
};

function ExportButtons({ data }: { data: Record<string, unknown>[] }) {
  function download(content: string, filename: string, mime: string) {
    const a = Object.assign(document.createElement("a"), {
      href: URL.createObjectURL(new Blob([content], { type: mime })), download: filename,
    });
    a.click(); URL.revokeObjectURL(a.href);
  }
  function toCSV() {
    const cols = Object.keys(data[0]);
    const rows = [cols.join(","), ...data.map((r) => cols.map((c) => JSON.stringify(String(r[c] ?? ""))).join(","))];
    download(rows.join("\n"), "results.csv", "text/csv");
  }
  return (
    <>
      <button style={btnStyle} onClick={() => download(JSON.stringify(data, null, 2), "results.json", "application/json")}>JSON</button>
      <button style={btnStyle} onClick={toCSV}>CSV</button>
    </>
  );
}
