"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { SSEEvent } from "@/types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface SSEState {
  status: string;
  messages: Array<{ time: string; text: string; type: string }>;
  rowsFound: number;
  resultId: string | null;
  error: string | null;
  isDone: boolean;
}

export function useJobSSE(jobId: string | null, autoConnect = true) {
  const [state, setState] = useState<SSEState>({
    status: "idle",
    messages: [],
    rowsFound: 0,
    resultId: null,
    error: null,
    isDone: false,
  });

  const esRef = useRef<EventSource | null>(null);
  const retryDelayRef = useRef(1000);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    if (!jobId) return;

    const es = new EventSource(`${BASE}/jobs/${jobId}/stream`);
    esRef.current = es;

    es.onopen = () => {
      retryDelayRef.current = 1000; // reset backoff on successful connect
    };

    es.onmessage = (event) => {
      try {
        const data: SSEEvent = JSON.parse(event.data);
        const time = new Date().toLocaleTimeString();

        setState((prev) => {
          const next = { ...prev };

          if (data.type === "status" && data.message) {
            next.status = data.message;
            next.messages = [
              ...prev.messages,
              { time, text: data.message, type: "status" },
            ];
          } else if (data.type === "progress") {
            next.rowsFound = data.rows_found ?? prev.rowsFound;
            next.messages = [
              ...prev.messages,
              { time, text: data.message ?? `${next.rowsFound} rows found`, type: "progress" },
            ];
          } else if (data.type === "done") {
            next.isDone = true;
            next.resultId = data.result_id ?? null;
            next.rowsFound = data.rows ?? prev.rowsFound;
            next.status = "completed";
            next.messages = [
              ...prev.messages,
              { time, text: data.message ?? "Done!", type: "done" },
            ];
          } else if (data.type === "error") {
            next.isDone = true;
            next.error = data.detail ?? "Unknown error";
            next.status = "failed";
            next.messages = [
              ...prev.messages,
              { time, text: data.detail ?? "Error", type: "error" },
            ];
          }

          return next;
        });

        if (data.type === "done" || data.type === "error") {
          es.close();
          esRef.current = null;
        }
      } catch {
        // ignore parse errors from keepalive comments
      }
    };

    es.onerror = () => {
      es.close();
      esRef.current = null;

      // Reconnect with exponential backoff (max 30s)
      const delay = retryDelayRef.current;
      retryDelayRef.current = Math.min(delay * 2, 30000);

      retryTimerRef.current = setTimeout(() => {
        if (!state.isDone) connect();
      }, delay);
    };
  }, [jobId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!autoConnect || !jobId) return;
    connect();
    return () => {
      esRef.current?.close();
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
    };
  }, [jobId, autoConnect, connect]);

  return state;
}
