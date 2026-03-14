"use client";

import { useState } from "react";
import { createAgentRun } from "@/lib/api";
import type { AgentRun } from "@/types";

interface Props {
  onStart: (run: AgentRun) => void;
}

const EXAMPLES = [
  "Find the top 10 AI startups that raised funding in 2024",
  "Collect Python developer job listings from RemoteOK",
  "Get the latest news headlines about OpenAI",
  "Find freelance web design jobs on Upwork",
];

export default function AgentGoalForm({ onStart }: Props) {
  const [goal, setGoal] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!goal.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const run = await createAgentRun(goal.trim());
      onStart(run);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to start agent");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ maxWidth: "640px", margin: "0 auto" }}>
      <div style={{ marginBottom: "28px" }}>
        <h1 style={{ fontSize: "20px", fontWeight: 600, color: "var(--text-primary)", marginBottom: "6px" }}>
          Web Agent
        </h1>
        <p style={{ fontSize: "13.5px", color: "var(--text-secondary)", lineHeight: 1.5 }}>
          Ask anything — the agent will search, browse, and return a direct answer.
          Structured data when you want a list; prose when you want a summary or explanation.
        </p>
      </div>

      <form onSubmit={handleSubmit} style={{ marginBottom: "24px" }}>
        <textarea
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="e.g. Find Python jobs in London, or: Summarize the top AI news from this week"
          rows={3}
          disabled={loading}
          style={{
            width: "100%",
            boxSizing: "border-box",
            padding: "10px 12px",
            fontSize: "13.5px",
            border: "1px solid var(--border)",
            borderRadius: "6px",
            background: "var(--surface)",
            color: "var(--text-primary)",
            resize: "vertical",
            fontFamily: "inherit",
            lineHeight: 1.5,
            outline: "none",
            marginBottom: "10px",
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleSubmit(e as unknown as React.FormEvent);
          }}
        />

        {error && (
          <div style={{
            padding: "8px 12px",
            background: "#fef2f2",
            border: "1px solid #fecaca",
            borderRadius: "5px",
            fontSize: "13px",
            color: "#dc2626",
            marginBottom: "10px",
          }}>
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={loading || !goal.trim()}
          style={{
            padding: "8px 18px",
            background: loading || !goal.trim() ? "var(--border)" : "var(--text-primary)",
            color: loading || !goal.trim() ? "var(--text-muted)" : "var(--surface)",
            border: "none",
            borderRadius: "5px",
            fontSize: "13.5px",
            fontWeight: 500,
            cursor: loading || !goal.trim() ? "not-allowed" : "pointer",
            transition: "background 0.15s",
          }}
        >
          {loading ? "Starting…" : "Run Agent"}
        </button>
        <span style={{ fontSize: "12px", color: "var(--text-muted)", marginLeft: "10px" }}>
          or Ctrl+Enter
        </span>
      </form>

      {/* Example prompts */}
      <div>
        <div style={{ fontSize: "11.5px", color: "var(--text-muted)", marginBottom: "8px", textTransform: "uppercase", letterSpacing: "0.06em" }}>
          Examples
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              onClick={() => setGoal(ex)}
              style={{
                background: "none",
                border: "1px solid var(--border)",
                borderRadius: "5px",
                padding: "7px 11px",
                fontSize: "13px",
                color: "var(--text-secondary)",
                textAlign: "left",
                cursor: "pointer",
                transition: "border-color 0.15s, color 0.15s",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--text-secondary)";
                (e.currentTarget as HTMLButtonElement).style.color = "var(--text-primary)";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--border)";
                (e.currentTarget as HTMLButtonElement).style.color = "var(--text-secondary)";
              }}
            >
              {ex}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
