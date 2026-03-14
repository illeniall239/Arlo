"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

interface RecentJob {
  id: string;
  url: string;
  prompt: string;
  status: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ── tiny icon components ─────────────────────────────────── */

function IconSearch() {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
      <circle cx="6.5" cy="6.5" r="4" stroke="currentColor" strokeWidth="1.4" />
      <path d="M10 10l3 3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}
function IconCalendar() {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
      <rect x="1.5" y="2.5" width="12" height="11" rx="1.5" stroke="currentColor" strokeWidth="1.4" />
      <path d="M5 1v3M10 1v3M1.5 6h12" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}
function IconEdit() {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
      <path
        d="M10.5 2.5l2 2L5 12H3v-2L10.5 2.5z"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
    </svg>
  );
}
function IconHelp() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
      <circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.3" />
      <path
        d="M5.5 5.5a1.5 1.5 0 012.9.5c0 1-1.4 1.5-1.4 2.5"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
      />
      <circle cx="7" cy="10.5" r="0.6" fill="currentColor" />
    </svg>
  );
}
function IconSettings() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
      <circle cx="7" cy="7" r="2.5" stroke="currentColor" strokeWidth="1.3" />
      <path
        d="M7 1v1.5M7 11.5V13M1 7h1.5M11.5 7H13M2.5 2.5l1 1M10.5 10.5l1 1M2.5 11.5l1-1M10.5 3.5l1-1"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
      />
    </svg>
  );
}
function IconLogout() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
      <path
        d="M5 2H2.5A1.5 1.5 0 001 3.5v7A1.5 1.5 0 002.5 12H5"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
      />
      <path d="M9 4.5L12 7l-3 2.5M5 7h7" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function IconGrid() {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
      <rect x="1.5" y="1.5" width="5" height="12" rx="1.2" fill="currentColor" />
      <rect x="8.5" y="1.5" width="5" height="5.5" rx="1.2" fill="currentColor" />
      <rect x="8.5" y="8.5" width="5" height="5" rx="1.2" fill="currentColor" />
    </svg>
  );
}

/* ── sidebar nav item ─────────────────────────────────────── */

function SidebarItem({
  icon,
  label,
  active,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  active?: boolean;
  onClick?: () => void;
}) {
  const [hovered, setHovered] = useState(false);
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "10px",
        padding: "7px 10px",
        borderRadius: "8px",
        background: active
          ? "var(--sidebar-active)"
          : hovered
          ? "var(--sidebar-hover)"
          : "transparent",
        cursor: "pointer",
        transition: "background 0.12s",
        marginBottom: "1px",
      }}
    >
      <span style={{ color: active ? "rgba(255,255,255,0.8)" : "rgba(255,255,255,0.4)", flexShrink: 0 }}>
        {icon}
      </span>
      <span
        style={{
          fontSize: "13.5px",
          color: active ? "rgba(255,255,255,0.92)" : "rgba(255,255,255,0.6)",
          fontWeight: active ? 450 : 400,
        }}
      >
        {label}
      </span>
    </div>
  );
}

/* ── main component ───────────────────────────────────────── */

export default function Sidebar() {
  const pathname = usePathname();
  const router   = useRouter();
  const [recentJobs, setRecentJobs] = useState<RecentJob[]>([]);
  const [open, setOpen] = useState(false);

  function loadRecent() {
    fetch(`${API_BASE}/jobs/?page_size=5`)
      .then((r) => r.json())
      .then((data) => {
        const items = data.data ?? [];
        setRecentJobs(Array.isArray(items) ? items.slice(0, 5) : []);
      })
      .catch(() => {});
  }

  useEffect(() => { loadRecent(); }, [pathname]);

  useEffect(() => {
    window.addEventListener("arlo:new-run", loadRecent);
    return () => window.removeEventListener("arlo:new-run", loadRecent);
  }, []);

  // Close drawer on route change
  useEffect(() => { setOpen(false); }, [pathname]);

  return (
    <>
      {/* Mobile top bar — CSS hides on desktop */}
      <div className="mob-header">
        <button className="mob-toggle" onClick={() => setOpen(true)} aria-label="Open menu">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M2 4h12M2 8h12M2 12h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </button>
        <div className="mob-header-logo">
          <div style={{ width: "24px", height: "24px", borderRadius: "50%", background: "#fff", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
              <rect x="2" y="2" width="5" height="5" rx="1" fill="#111" />
              <rect x="9" y="2" width="5" height="5" rx="1" fill="#111" />
              <rect x="2" y="9" width="5" height="5" rx="1" fill="#111" />
              <rect x="9" y="9" width="5" height="5" rx="1" fill="#c9f135" />
            </svg>
          </div>
          <span style={{ fontSize: "15px", fontWeight: 600, color: "#fff", letterSpacing: "-0.01em" }}>Arlo</span>
        </div>
      </div>

      {/* Backdrop — only when drawer is open */}
      {open && <div className="sidebar-backdrop" onClick={() => setOpen(false)} />}

      {/* sidebar-drawer class has no effect on desktop (only activates in mobile media query) */}
      <aside
        className={`sidebar-drawer${open ? " open" : ""}`}
        style={{
          width: "240px",
          flexShrink: 0,
          background: "var(--sidebar-bg)",
          display: "flex",
          flexDirection: "column",
          height: "100%",
          color: "var(--sidebar-text)",
        }}
      >
      {/* ── logo row ── */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          padding: "20px 16px 14px",
          gap: "10px",
        }}
      >
        <div
          style={{
            width: "30px",
            height: "30px",
            borderRadius: "50%",
            background: "#ffffff",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <rect x="2" y="2" width="5" height="5" rx="1" fill="#111" />
            <rect x="9" y="2" width="5" height="5" rx="1" fill="#111" />
            <rect x="2" y="9" width="5" height="5" rx="1" fill="#111" />
            <rect x="9" y="9" width="5" height="5" rx="1" fill="#c9f135" />
          </svg>
        </div>
        <span style={{ fontSize: "15px", fontWeight: 600, color: "#fff", flex: 1, letterSpacing: "-0.01em" }}>
          Arlo
        </span>
      </div>

      {/* ── primary nav ── */}
      <div style={{ padding: "4px 8px 10px" }}>
        {/* New research */}
        <div
          onClick={() => { router.push(`/dashboard?new=${Date.now()}`); setOpen(false); }}
          style={{ textDecoration: "none", display: "block", cursor: "pointer" }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "10px",
              padding: "8px 10px",
              borderRadius: "8px",
              background: pathname === "/dashboard" ? "var(--sidebar-active)" : "transparent",
              marginBottom: "2px",
              cursor: "pointer",
            }}
          >
            <span style={{ color: "rgba(255,255,255,0.55)", flexShrink: 0 }}>
              <IconEdit />
            </span>
            <span style={{ fontSize: "13.5px", color: "rgba(255,255,255,0.82)", flex: 1, fontWeight: 450 }}>
              New research
            </span>
            <kbd
              style={{
                fontSize: "10px",
                padding: "2px 5px",
                borderRadius: "4px",
                background: "rgba(255,255,255,0.09)",
                color: "rgba(255,255,255,0.3)",
                fontFamily: "inherit",
                border: "none",
                letterSpacing: "0.01em",
              }}
            >
              ⌘ N
            </kbd>
          </div>
        </div>

        {/* All jobs */}
        <Link href="/jobs" style={{ textDecoration: "none", display: "block" }} onClick={() => setOpen(false)}>
          <SidebarItem icon={<IconSearch />} label="All jobs" active={pathname === "/jobs"} />
        </Link>

        {/* Schedules */}
        <Link href="/schedules" style={{ textDecoration: "none", display: "block" }} onClick={() => setOpen(false)}>
          <SidebarItem icon={<IconCalendar />} label="Schedules" active={pathname === "/schedules"} />
        </Link>
      </div>

      {/* ── divider ── */}
      <div style={{ height: "1px", background: "var(--sidebar-border)", margin: "0 8px" }} />

      {/* ── recent ── */}
      <div style={{ padding: "12px 8px 8px", flex: 1, overflow: "hidden" }}>
        <div
          style={{
            fontSize: "11px",
            color: "rgba(255,255,255,0.28)",
            letterSpacing: "0.07em",
            textTransform: "uppercase",
            padding: "0 10px",
            marginBottom: "6px",
          }}
        >
          Recent
        </div>
        {recentJobs.length === 0 ? (
          <div style={{ padding: "0 10px", fontSize: "12.5px", color: "rgba(255,255,255,0.2)" }}>
            No recent jobs
          </div>
        ) : (
          recentJobs.map((job) => {
            let label = job.prompt;
            try { label = new URL(job.url).hostname.replace(/^www\./, ""); } catch {}
            const statusDot: Record<string, string> = {
              completed: "#c9f135",
              running: "#f5a623",
              failed: "#ff5c5c",
              pending: "rgba(255,255,255,0.2)",
            };
            const dotColor = statusDot[job.status] ?? "rgba(255,255,255,0.2)";
            return (
              <Link key={job.id} href={`/jobs/${job.id}`} style={{ textDecoration: "none", display: "block" }} onClick={() => setOpen(false)}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    padding: "6px 10px",
                    borderRadius: "7px",
                    fontSize: "13px",
                    color: "rgba(255,255,255,0.5)",
                    cursor: "pointer",
                    overflow: "hidden",
                    transition: "background 0.12s, color 0.12s",
                    marginBottom: "1px",
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLDivElement).style.background = "var(--sidebar-hover)";
                    (e.currentTarget as HTMLDivElement).style.color = "rgba(255,255,255,0.75)";
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLDivElement).style.background = "transparent";
                    (e.currentTarget as HTMLDivElement).style.color = "rgba(255,255,255,0.5)";
                  }}
                >
                  <div style={{ width: "6px", height: "6px", borderRadius: "50%", background: dotColor, flexShrink: 0 }} />
                  <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{label}</span>
                </div>
              </Link>
            );
          })
        )}
      </div>


    </aside>
    </>
  );
}
