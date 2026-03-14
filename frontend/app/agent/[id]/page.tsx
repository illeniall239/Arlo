"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { createAgentRun, fetchAgentRun } from "@/lib/api";
import AgentTrace from "@/components/agent/AgentTrace";

interface Turn { goal: string; runId: string; key: number; response?: string }

function IconSend() {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
      <path d="M7.5 2.5V12.5M3 7l4.5-4.5L12 7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function AgentRunPage() {
  const { id }   = useParams<{ id: string }>();
  const router   = useRouter();
  const [turns, setTurns]     = useState<Turn[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [followup, setFollowup]   = useState("");
  const [loading, setLoading]     = useState(false);

  function buildContext(completedTurns: Turn[]): string | undefined {
    const filled = completedTurns.filter((t) => t.response);
    if (filled.length === 0) return undefined;
    return filled
      .map((t, i) => `Turn ${i + 1}:\nUser: ${t.goal}\nAssistant: ${t.response}`)
      .join("\n\n");
  }
  const bottomRef  = useRef<HTMLDivElement>(null);
  const keyRef     = useRef(1);

  // Load the initial run
  useEffect(() => {
    fetchAgentRun(id)
      .then((r) => {
        setTurns([{ goal: r.goal, runId: id, key: 0 }]);
        const terminal = ["completed", "failed", "cancelled"];
        setIsRunning(!terminal.includes(r.status));
      })
      .catch(() => setTurns([{ goal: "", runId: id, key: 0 }]));
  }, [id]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  const handleTurnComplete = useCallback((_status: string, response?: string) => {
    setIsRunning(false);
    if (response) {
      setTurns((prev) => prev.map((t, i) => i === prev.length - 1 ? { ...t, response } : t));
    }
  }, []);

  async function handleFollowup() {
    if (!followup.trim() || loading || isRunning) return;
    setLoading(true);
    try {
      const context = buildContext(turns);
      const run = await createAgentRun(followup.trim(), context);
      setTurns((prev) => [...prev, { goal: followup.trim(), runId: run.id, key: keyRef.current++ }]);
      setIsRunning(true);
      setFollowup("");
    } catch { /* ignore */ }
    setLoading(false);
  }

  if (turns.length === 0) {
    return <div style={{ padding: "28px 32px" }}><p style={{ fontSize: "13.5px", color: "var(--text-muted)" }}>Loading…</p></div>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>

      {/* Header */}
      <div style={{ padding: "14px 28px 0", flexShrink: 0 }}>
        <button
          onClick={() => router.push("/history")}
          style={{ background: "none", border: "none", cursor: "pointer", fontSize: "13px", color: "var(--text-secondary)", display: "flex", alignItems: "center", gap: "5px", padding: "4px 0" }}
          onMouseEnter={(e) => ((e.currentTarget as HTMLButtonElement).style.color = "var(--text-primary)")}
          onMouseLeave={(e) => ((e.currentTarget as HTMLButtonElement).style.color = "var(--text-secondary)")}
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M9 2L4 7l5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          History
        </button>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: "auto", padding: "28px 0 0" }}>
        <div style={{ maxWidth: "720px", margin: "0 auto", padding: "0 28px", display: "flex", flexDirection: "column", gap: "36px" }}>
          {turns.map((turn, i) => (
            <AgentTrace
              key={turn.key}
              runId={turn.runId}
              goal={turn.goal}
              showCancel={i === turns.length - 1 && isRunning}
              onComplete={i === turns.length - 1 ? handleTurnComplete : undefined}
            />
          ))}
          <div ref={bottomRef} style={{ height: "16px" }} />
        </div>
      </div>

      {/* Follow-up input */}
      <div style={{ padding: "12px 28px 20px", flexShrink: 0 }}>
        <div style={{ maxWidth: "720px", margin: "0 auto" }}>
          <div style={{ background: "var(--surface)", borderRadius: "16px", border: "1px solid var(--border)", boxShadow: "0 2px 12px rgba(0,0,0,0.06)", padding: "12px 14px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <input
                value={followup}
                onChange={(e) => setFollowup(e.target.value)}
                placeholder={isRunning ? "Waiting for response…" : "Ask a follow-up…"}
                disabled={loading || isRunning}
                style={{ flex: 1, border: "none", outline: "none", fontSize: "14px", color: "var(--text-primary)", background: "transparent", fontFamily: "inherit" }}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleFollowup(); } }}
              />
              <button
                onClick={handleFollowup}
                disabled={loading || isRunning || !followup.trim()}
                style={{ width: "32px", height: "32px", borderRadius: "50%", border: "none", background: loading || isRunning || !followup.trim() ? "#d4d4ce" : "var(--text-primary)", display: "flex", alignItems: "center", justifyContent: "center", cursor: loading || isRunning || !followup.trim() ? "not-allowed" : "pointer", color: "#fff", transition: "background 0.15s", flexShrink: 0 }}
              >
                {loading ? (
                  <span style={{ width: "11px", height: "11px", border: "2px solid rgba(255,255,255,0.4)", borderTopColor: "#fff", borderRadius: "50%", display: "inline-block", animation: "spin 0.6s linear infinite" }} />
                ) : <IconSend />}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
