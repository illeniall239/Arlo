"use client";

import React, { useMemo, useState } from "react";
import type { Diff } from "@/types";

interface Props {
  data: Record<string, unknown>[];
  schema: string[];
  diff?: Diff | null;
}

const PAGE_SIZE = 25;

function rowKey(row: Record<string, unknown>): string {
  const url = row.url ?? row.profile_url ?? row.link;
  return url ? String(url) : JSON.stringify(row);
}

function cellValue(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export default function ResultsTable({ data, schema, diff }: Props) {
  const [search, setSearch] = useState("");
  const [page, setPage]     = useState(1);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [sortKey, setSortKey]   = useState<string | null>(null);
  const [sortAsc, setSortAsc]   = useState(true);

  const columns = schema.length > 0 ? schema : Object.keys(data[0] ?? {});

  const addedKeys = useMemo(
    () => new Set((diff?.added_records ?? []).map(rowKey)),
    [diff]
  );
  const changedMap = useMemo(() => {
    const m = new Map<string, Record<string, { from: unknown; to: unknown }>>();
    for (const cr of diff?.changed_records ?? []) m.set(cr.key, cr.changes);
    return m;
  }, [diff]);

  const filtered = data.filter((row) =>
    search
      ? columns.some((col) => cellValue(row[col]).toLowerCase().includes(search.toLowerCase()))
      : true
  );

  const sorted = sortKey
    ? [...filtered].sort((a, b) => {
        const av = a[sortKey], bv = b[sortKey];
        if (typeof av === "number" && typeof bv === "number")
          return sortAsc ? av - bv : bv - av;
        return sortAsc
          ? String(av ?? "").localeCompare(String(bv ?? ""), undefined, { numeric: true })
          : String(bv ?? "").localeCompare(String(av ?? ""), undefined, { numeric: true });
      })
    : filtered;

  const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const pageData   = sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const handleSort = (col: string) => {
    if (sortKey === col) setSortAsc(!sortAsc);
    else { setSortKey(col); setSortAsc(true); }
    setPage(1);
  };

  return (
    <div>
      {/* Search */}
      <div style={{ marginBottom: "10px", position: "relative" }}>
        <svg width="13" height="13" viewBox="0 0 13 13" fill="none" style={{ position: "absolute", left: "11px", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)", pointerEvents: "none" }}>
          <circle cx="5.5" cy="5.5" r="3.8" stroke="currentColor" strokeWidth="1.3" />
          <path d="M9 9l2.5 2.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
        </svg>
        <input
          type="text"
          placeholder="Filter records…"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          style={{
            width: "100%",
            border: "1px solid var(--border)",
            borderRadius: "8px",
            padding: "8px 12px 8px 32px",
            fontSize: "13px",
            color: "var(--text-primary)",
            background: "var(--surface)",
            outline: "none",
            fontFamily: "inherit",
            transition: "border-color 0.15s",
          }}
          onFocus={e => (e.target.style.borderColor = "var(--border-strong)")}
          onBlur={e => (e.target.style.borderColor = "var(--border)")}
        />
        {search && (
          <span style={{ position: "absolute", right: "11px", top: "50%", transform: "translateY(-50%)", fontSize: "11px", color: "var(--text-muted)" }}>
            {filtered.length} match{filtered.length !== 1 ? "es" : ""}
          </span>
        )}
      </div>

      {/* Table */}
      <div style={{ border: "1px solid var(--border)", borderRadius: "10px", overflow: "hidden", background: "var(--surface)" }}>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: "var(--page-bg)" }}>
                <th style={thStyle}>#</th>
                {columns.map((col) => (
                  <th key={col} style={{ ...thStyle, cursor: "pointer" }} onClick={() => handleSort(col)}>
                    <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                      {col.replace(/_/g, " ")}
                      {sortKey === col ? (
                        <span style={{ color: "var(--text-secondary)", fontSize: "10px" }}>{sortAsc ? "↑" : "↓"}</span>
                      ) : (
                        <span style={{ color: "var(--border-strong)", fontSize: "10px", opacity: 0.5 }}>↕</span>
                      )}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pageData.map((row, i) => {
                const rowIdx = (page - 1) * PAGE_SIZE + i;
                const isExpandedRow = expanded === rowIdx;
                const key = rowKey(row);
                const isAdded   = addedKeys.has(key);
                const changedFields = changedMap.get(key);
                const isChanged = !!changedFields;

                const rowAccent = isAdded ? "#f0fdf4" : isChanged ? "#fffbeb" : undefined;

                return (
                  <React.Fragment key={rowIdx}>
                    <tr
                      onClick={() => setExpanded(isExpandedRow ? null : rowIdx)}
                      style={{
                        cursor: "pointer",
                        background: rowAccent ?? (isExpandedRow ? "var(--page-bg)" : "var(--surface)"),
                        transition: "background 0.1s",
                        borderLeft: isAdded ? "2px solid #16a34a" : isChanged ? "2px solid #ca8a04" : "2px solid transparent",
                      }}
                      onMouseEnter={e => { if (!rowAccent && !isExpandedRow) e.currentTarget.style.background = "var(--page-bg)"; }}
                      onMouseLeave={e => { if (!rowAccent && !isExpandedRow) e.currentTarget.style.background = "var(--surface)"; }}
                    >
                      <td style={{ ...tdStyle, color: "var(--text-muted)", fontSize: "11px", fontFamily: "var(--font-geist-mono), monospace", width: "40px" }}>
                        {rowIdx + 1}
                      </td>
                      {columns.map((col) => {
                        const val = cellValue(row[col]);
                        const isUrl = val.startsWith("http://") || val.startsWith("https://");
                        return (
                          <td key={col} style={tdStyle}>
                            {isUrl ? (
                              <a
                                href={val} target="_blank" rel="noopener noreferrer"
                                onClick={e => e.stopPropagation()}
                                style={{ color: "var(--text-secondary)", textDecoration: "none", fontFamily: "var(--font-geist-mono), monospace", fontSize: "12px" }}
                                onMouseEnter={e => (e.currentTarget.style.color = "var(--text-primary)")}
                                onMouseLeave={e => (e.currentTarget.style.color = "var(--text-secondary)")}
                              >
                                {val.length > 40 ? val.slice(0, 40) + "…" : val}
                              </a>
                            ) : (
                              <span style={{ display: "block", maxWidth: "240px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                {val}
                              </span>
                            )}
                          </td>
                        );
                      })}
                    </tr>

                    {isExpandedRow && (
                      <tr>
                        <td colSpan={columns.length + 1} style={{ padding: "16px 18px", background: "#0e0e0e", borderBottom: "1px solid var(--border)" }}>
                          {changedFields && (
                            <div style={{ marginBottom: "12px" }}>
                              <p style={{ fontSize: "11px", fontWeight: 500, color: "rgba(255,255,255,0.3)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "8px" }}>
                                Changed fields
                              </p>
                              <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                                {Object.entries(changedFields).map(([field, { from, to }]) => (
                                  <div key={field} style={{ fontSize: "12px", display: "flex", gap: "10px", alignItems: "baseline", fontFamily: "var(--font-geist-mono), monospace" }}>
                                    <span style={{ color: "rgba(255,255,255,0.3)", minWidth: "120px" }}>{field}</span>
                                    <span style={{ color: "#f87171", textDecoration: "line-through" }}>{String(from ?? "—")}</span>
                                    <span style={{ color: "rgba(255,255,255,0.2)" }}>→</span>
                                    <span style={{ color: "#c9f135" }}>{String(to ?? "—")}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                          <pre style={{ fontSize: "12px", color: "rgba(255,255,255,0.55)", margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-all", fontFamily: "var(--font-geist-mono), 'SF Mono', monospace", lineHeight: 1.6 }}>
                            {JSON.stringify(row, null, 2)}
                          </pre>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: "12px" }}>
          <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>
            Page {page} of {totalPages} · {sorted.length} records
          </span>
          <div style={{ display: "flex", gap: "4px" }}>
            <NavBtn onClick={() => setPage(Math.max(1, page - 1))} disabled={page === 1} label="← Prev" />
            <NavBtn onClick={() => setPage(Math.min(totalPages, page + 1))} disabled={page === totalPages} label="Next →" />
          </div>
        </div>
      )}
    </div>
  );
}

const thStyle: React.CSSProperties = {
  padding: "9px 12px",
  textAlign: "left",
  fontSize: "11px",
  fontWeight: 500,
  color: "var(--text-muted)",
  letterSpacing: "0.05em",
  textTransform: "uppercase",
  borderBottom: "1px solid var(--border)",
  userSelect: "none",
  whiteSpace: "nowrap",
};

const tdStyle: React.CSSProperties = {
  padding: "10px 12px",
  fontSize: "13px",
  color: "var(--text-primary)",
  borderBottom: "1px solid var(--border)",
  verticalAlign: "middle",
};

function NavBtn({ onClick, disabled, label }: { onClick: () => void; disabled: boolean; label: string }) {
  return (
    <button
      onClick={onClick} disabled={disabled}
      style={{
        padding: "5px 12px", fontSize: "12px",
        border: "1px solid var(--border)", borderRadius: "7px",
        background: "var(--surface)", color: "var(--text-secondary)",
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.35 : 1,
        fontFamily: "inherit", transition: "border-color 0.12s",
      }}
      onMouseEnter={e => { if (!disabled) e.currentTarget.style.borderColor = "var(--border-strong)"; }}
      onMouseLeave={e => { e.currentTarget.style.borderColor = "var(--border)"; }}
    >
      {label}
    </button>
  );
}
