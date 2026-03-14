"use client";

import { useEffect, useState } from "react";
import { fetchSettings, updateSettings } from "@/lib/api";
import type { AppSettings } from "@/types";

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
  letterSpacing: "0.01em",
};

const hintStyle: React.CSSProperties = {
  fontSize: "11.5px",
  color: "var(--text-muted)",
  marginTop: "5px",
  lineHeight: 1.5,
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: "0" }}>
      <div style={{
        fontSize: "11px", fontWeight: 500, color: "var(--text-muted)",
        letterSpacing: "0.07em", textTransform: "uppercase", marginBottom: "12px",
      }}>
        {title}
      </div>
      {children}
    </div>
  );
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [proxyText, setProxyText] = useState("");
  const [saving, setSaving]     = useState(false);
  const [saved, setSaved]       = useState(false);

  useEffect(() => {
    fetchSettings().then((s) => {
      setSettings(s);
      setProxyText(s.proxy_list.join("\n"));
    });
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!settings) return;
    setSaving(true);
    try {
      const proxies = proxyText.split("\n").map((p) => p.trim()).filter(Boolean);
      const updated = await updateSettings({ ...settings, proxy_list: proxies });
      setSettings(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) { console.error(e); }
    setSaving(false);
  };

  if (!settings) {
    return (
      <div style={{ padding: "28px 32px" }}>
        <p style={{ fontSize: "13.5px", color: "var(--text-muted)" }}>Loading…</p>
      </div>
    );
  }

  return (
    <div style={{ padding: "28px 32px", maxWidth: "560px", width: "100%" }}>

      {/* Header */}
      <div style={{ marginBottom: "28px" }}>
        <h1 style={{ fontSize: "20px", fontWeight: 650, color: "var(--text-primary)", letterSpacing: "-0.02em", marginBottom: "4px" }}>
          Settings
        </h1>
        <p style={{ fontSize: "13.5px", color: "var(--text-secondary)" }}>Configure scraping behaviour and defaults.</p>
      </div>

      <form onSubmit={handleSave} style={{ display: "flex", flexDirection: "column", gap: "1px" }}>

        {/* Fetcher */}
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "10px 10px 0 0", padding: "18px 20px" }}>
          <Section title="Fetcher">
            <label style={labelStyle}>Default fetcher</label>
            <select
              value={settings.default_fetcher}
              onChange={(e) => setSettings({ ...settings, default_fetcher: e.target.value })}
              style={{ ...inputStyle, cursor: "pointer" }}
              onFocus={(e) => (e.currentTarget.style.borderColor = "var(--border-strong)")}
              onBlur={(e) => (e.currentTarget.style.borderColor = "var(--border)")}
            >
              <option value="auto">Auto — AI decides</option>
              <option value="Fetcher">Fetcher — static HTML</option>
              <option value="StealthyFetcher">StealthyFetcher — Cloudflare bypass</option>
              <option value="DynamicFetcher">DynamicFetcher — JavaScript SPA</option>
            </select>
          </Section>
        </div>

        {/* Rate limits */}
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderTop: "none", padding: "18px 20px" }}>
          <Section title="Rate limiting">
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
              <div>
                <label style={labelStyle}>Concurrency limit</label>
                <input
                  type="number" min={1} max={10} value={settings.concurrency_limit}
                  onChange={(e) => setSettings({ ...settings, concurrency_limit: parseInt(e.target.value) })}
                  style={inputStyle}
                  onFocus={(e) => (e.currentTarget.style.borderColor = "var(--border-strong)")}
                  onBlur={(e) => (e.currentTarget.style.borderColor = "var(--border)")}
                />
                <p style={hintStyle}>Max parallel jobs</p>
              </div>
              <div>
                <label style={labelStyle}>Rate limit delay (s)</label>
                <input
                  type="number" min={0} step={0.5} value={settings.rate_limit_delay}
                  onChange={(e) => setSettings({ ...settings, rate_limit_delay: parseFloat(e.target.value) })}
                  style={inputStyle}
                  onFocus={(e) => (e.currentTarget.style.borderColor = "var(--border-strong)")}
                  onBlur={(e) => (e.currentTarget.style.borderColor = "var(--border)")}
                />
                <p style={hintStyle}>Seconds between requests</p>
              </div>
            </div>
          </Section>
        </div>

        {/* Crawl behaviour */}
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderTop: "none", padding: "18px 20px" }}>
          <Section title="Crawl behaviour">
            <label style={{
              display: "flex", alignItems: "center", gap: "10px",
              cursor: "pointer", userSelect: "none",
            }}>
              <div
                onClick={() => setSettings({ ...settings, respect_robots_txt: !settings.respect_robots_txt })}
                style={{
                  width: "36px", height: "20px", borderRadius: "10px",
                  background: settings.respect_robots_txt ? "var(--text-primary)" : "var(--border-strong)",
                  position: "relative", cursor: "pointer", transition: "background 0.2s", flexShrink: 0,
                }}
              >
                <div style={{
                  position: "absolute", top: "2px",
                  left: settings.respect_robots_txt ? "18px" : "2px",
                  width: "16px", height: "16px", borderRadius: "50%", background: "#fff",
                  transition: "left 0.2s", boxShadow: "0 1px 3px rgba(0,0,0,0.2)",
                }} />
              </div>
              <span style={{ fontSize: "13.5px", color: "var(--text-primary)" }}>Respect robots.txt</span>
            </label>
          </Section>
        </div>

        {/* Proxies */}
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderTop: "none", borderRadius: "0 0 10px 10px", padding: "18px 20px" }}>
          <Section title="Proxies">
            <label style={labelStyle}>Proxy list</label>
            <textarea
              value={proxyText}
              onChange={(e) => setProxyText(e.target.value)}
              rows={4}
              placeholder={"http://user:pass@host:8080\nhttp://user:pass@host2:8080"}
              style={{
                ...inputStyle, resize: "vertical", lineHeight: 1.6,
                fontFamily: "var(--font-geist-mono), monospace", fontSize: "12px",
              }}
              onFocus={(e) => (e.currentTarget.style.borderColor = "var(--border-strong)")}
              onBlur={(e) => (e.currentTarget.style.borderColor = "var(--border)")}
            />
            <p style={hintStyle}>One proxy URL per line</p>
          </Section>
        </div>

        {/* Save */}
        <button
          type="submit"
          disabled={saving}
          style={{
            marginTop: "16px",
            width: "100%",
            padding: "10px",
            background: saved ? "#059669" : saving ? "var(--border-strong)" : "var(--text-primary)",
            color: "#fff",
            border: "none",
            borderRadius: "8px",
            fontSize: "13.5px",
            fontWeight: 500,
            cursor: saving ? "not-allowed" : "pointer",
            fontFamily: "inherit",
            transition: "background 0.15s",
          }}
        >
          {saving ? "Saving…" : saved ? "Saved" : "Save settings"}
        </button>

      </form>
    </div>
  );
}
