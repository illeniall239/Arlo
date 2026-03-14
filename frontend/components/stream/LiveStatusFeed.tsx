"use client";

import { useEffect, useRef } from "react";
import { useJobSSE } from "@/hooks/useJobSSE";

const dotColor: Record<string, string> = {
  status:   "#60a5fa",
  progress: "#c9f135",
  done:     "#c9f135",
  error:    "#f87171",
};

const textColor: Record<string, string> = {
  status:   "rgba(255,255,255,0.55)",
  progress: "rgba(255,255,255,0.75)",
  done:     "#c9f135",
  error:    "#f87171",
};

const TERMINAL = new Set(["completed", "failed", "cancelled"]);

export default function LiveStatusFeed({ jobId, jobStatus }: { jobId: string; jobStatus?: string }) {
  const isTerminal = TERMINAL.has(jobStatus ?? "");
  const { messages, isDone, error } = useJobSSE(jobId, !isTerminal);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const emptyFallback = isTerminal
    ? jobStatus === "completed" ? "✓ Job completed"
    : jobStatus === "failed"    ? "✗ Job failed"
    : "— Job was cancelled"
    : "Waiting for job to start…";

  const emptyColor = isTerminal
    ? jobStatus === "completed" ? "#c9f135"
    : jobStatus === "failed"    ? "#f87171"
    : "rgba(255,255,255,0.3)"
    : "rgba(255,255,255,0.2)";

  return (
    <div style={{
      background: "#0e0e0e",
      border: "1px solid rgba(255,255,255,0.07)",
      borderRadius: "10px",
      padding: "16px 18px",
      fontFamily: "var(--font-geist-mono), 'SF Mono', monospace",
      fontSize: "12px",
      lineHeight: "1.7",
      height: "200px",
      overflowY: "auto",
      display: "flex",
      flexDirection: "column",
    }}>
      {messages.length === 0 && (
        <span style={{ color: emptyColor, margin: "auto auto", fontFamily: "inherit" }}>
          {emptyFallback}
        </span>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: "0px" }}>
        {messages.map((m, i) => (
          <div key={i} style={{ display: "flex", gap: "12px", alignItems: "flex-start", padding: "1px 0" }}>
            <span style={{ color: "rgba(255,255,255,0.2)", flexShrink: 0, userSelect: "none", minWidth: "60px" }}>
              {m.time}
            </span>
            <span style={{
              width: "5px", height: "5px", borderRadius: "50%",
              background: dotColor[m.type] ?? "rgba(255,255,255,0.25)",
              flexShrink: 0, marginTop: "6px",
            }} />
            <span style={{ color: textColor[m.type] ?? "rgba(255,255,255,0.6)", wordBreak: "break-word" }}>
              {m.text}
            </span>
          </div>
        ))}

        {isDone && !error && (
          <div style={{ display: "flex", gap: "12px", alignItems: "center", marginTop: "8px", paddingTop: "8px", borderTop: "1px solid rgba(255,255,255,0.06)" }}>
            <span style={{ color: "rgba(255,255,255,0.2)", minWidth: "60px", userSelect: "none" }} />
            <span style={{ color: "#c9f135", fontSize: "12px" }}>✓</span>
            <span style={{ color: "#c9f135" }}>Done</span>
          </div>
        )}

        {error && (
          <div style={{ display: "flex", gap: "12px", alignItems: "center", marginTop: "8px", paddingTop: "8px", borderTop: "1px solid rgba(255,255,255,0.06)" }}>
            <span style={{ color: "rgba(255,255,255,0.2)", minWidth: "60px", userSelect: "none" }} />
            <span style={{ color: "#f87171" }}>✗ {error}</span>
          </div>
        )}
      </div>

      <div ref={bottomRef} />
    </div>
  );
}
