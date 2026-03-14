"use client";

import { getExportUrl } from "@/lib/api";

const btnStyle: React.CSSProperties = {
  padding: "6px 12px",
  fontSize: "12.5px",
  border: "1px solid var(--border)",
  borderRadius: "5px",
  background: "var(--surface)",
  color: "var(--text-secondary)",
  cursor: "pointer",
  fontFamily: "inherit",
  transition: "border-color 0.15s, color 0.15s",
};

export default function ExportButtons({ resultId }: { resultId: string }) {
  return (
    <div style={{ display: "flex", gap: "6px" }}>
      <button
        style={btnStyle}
        onClick={() => window.open(getExportUrl(resultId, "json"), "_blank")}
        onMouseEnter={e => { e.currentTarget.style.borderColor = "var(--border-strong)"; e.currentTarget.style.color = "var(--text-primary)"; }}
        onMouseLeave={e => { e.currentTarget.style.borderColor = "var(--border)"; e.currentTarget.style.color = "var(--text-secondary)"; }}
      >
        Export JSON
      </button>
      <button
        style={{ ...btnStyle, background: "var(--accent)", border: "1px solid var(--accent)", color: "#fff" }}
        onClick={() => window.open(getExportUrl(resultId, "csv"), "_blank")}
        onMouseEnter={e => { e.currentTarget.style.background = "var(--accent-hover)"; }}
        onMouseLeave={e => { e.currentTarget.style.background = "var(--accent)"; }}
      >
        Export CSV
      </button>
    </div>
  );
}
