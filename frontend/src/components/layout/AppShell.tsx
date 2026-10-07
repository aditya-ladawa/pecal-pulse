"use client";
import { useEffect, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  UsersRound,
  ListTodo,
  PanelLeftClose,
  PanelLeftOpen,
  Sparkles,
  ArrowUpRight,
  FlaskConical,
  Check,
  X,
} from "lucide-react";
import { useSalesStore } from "@/modules/sales/store";
import {
  getV2Bootstrap,
  getV2Customers,
  getV2Followups,
} from "@/modules/sales/api";
import { defaultFilters } from "@/modules/sales/store";
import { IntegratedWorkspace } from "@/modules/sales/IntegratedWorkspace";
import {
  SalesAssistant,
  SalesAssistantProvider,
} from "@/modules/chat/SalesAssistant";
const nav = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/customers", label: "Customers", icon: UsersRound },
  { href: "/follow-ups", label: "Follow-ups", icon: ListTodo },
];
export function AppShell({ children }: { children: ReactNode }) {
  const v2 = useSalesStore((s) => s.v2),
    v2Error = useSalesStore((s) => s.v2Error);
  const pathname = usePathname(),
    router = useRouter(),
    collapsed = useSalesStore((s) => s.sidebarCollapsed),
    assistantOpen = useSalesStore((s) => s.assistantOpen),
    request = useSalesStore((s) => s.requestedPage),
    notice = useSalesStore((s) => s.notice),
    status = useSalesStore((s) => s.apiStatus),
    openTasks = useSalesStore(
      (s) => s.data.followups.filter((f) => f.status === "open").length,
    ),
    set = useSalesStore((s) => s.set);
  useEffect(() => {
    let active = true;
    getV2Bootstrap()
      .then(async (boot) => {
        const [list, tasks] = await Promise.all([
          getV2Customers(boot.metadata.snapshot_id, defaultFilters),
          getV2Followups(boot.metadata.snapshot_id),
        ]);
        if (active)
          set({
            v2: boot,
            v2List: list,
            selectedId: list.items[0]?.profile.customer_id || "",
            data: { ...useSalesStore.getState().data, followups: tasks.items },
            apiStatus: "connected",
            v2Loading: false,
          });
      })
      .catch((e) => {
        if (active)
          set({ apiStatus: "offline", v2Loading: false, v2Error: e.message });
      });
    return () => {
      active = false;
    };
  }, [set]);
  useEffect(() => {
    if (request) {
      router.push(request === "dashboard" ? "/" : `/${request}`);
      set({ requestedPage: null });
    }
  }, [request, router, set]);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => set({ notice: "" }), 3500);
    return () => clearTimeout(timer);
  }, [notice, set]);
  return (
    <SalesAssistantProvider>
      <div
        className={`app-shell ${collapsed ? "collapsed" : ""} ${assistantOpen ? "assistant-open" : ""}`}
      >
        <aside className="sidebar">
          <Link href="/" className="brand" aria-label="PeCal Pulse dashboard">
            <span className="brand-icon">
              p<span />
            </span>
            <span className="brand-name">
              PeCal<span>pulse</span>
            </span>
          </Link>
          <button
            className="collapse-button"
            onClick={() => set({ sidebarCollapsed: !collapsed })}
            aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
          >
            {collapsed ? (
              <PanelLeftOpen size={18} />
            ) : (
              <PanelLeftClose size={18} />
            )}
          </button>
          <div className="nav-label">YOUR WORKSPACE</div>
          <nav aria-label="Main navigation">
            {nav.map((n) => (
              <Link
                key={n.href}
                href={n.href}
                className={`nav-link ${pathname === n.href ? "active" : ""}`}
                title={n.label}
              >
                <n.icon size={19} />
                <span>{n.label}</span>
                {n.href === "/follow-ups" && <i>{openTasks}</i>}
              </Link>
            ))}
          </nav>
          <div className="sidebar-bottom">
            <div className="help-card">
              <span className="tiny-spark">
                <Sparkles size={19} />
              </span>
              <h3>A clearer next step.</h3>
              <p>Ask Pulse to help you explore your customer workspace.</p>
              <button onClick={() => set({ assistantOpen: true })}>
                Meet your assistant <ArrowUpRight size={15} />
              </button>
            </div>
            <div className="profile">
              <div className="profile-avatar">AM</div>
              <div>
                <strong>Alex Meyer</strong>
                <small>Demo representative</small>
              </div>
            </div>
          </div>
        </aside>
        <main className="main">
          <header className="topbar">
            <div className="breadcrumb">
              Workspace <span>/</span>{" "}
              <strong>
                {nav.find((n) => n.href === pathname)?.label || "Dashboard"}
              </strong>
            </div>
            <div className="topbar-right">
              <span className={`connection ${status}`}>
                <i />
                {status === "connected"
                  ? "Local API connected"
                  : status === "offline"
                    ? "Offline preview"
                    : "Connecting API"}
              </span>
              <span className="date-pill">07 Oct 2026</span>
              <button
                className="profile-avatar small-profile"
                onClick={() => set({ assistantOpen: !assistantOpen })}
                aria-label="Toggle sales assistant"
              >
                AM
              </button>
            </div>
          </header>
          <div className="mock-banner">
            <FlaskConical size={14} />
            <span>
              <strong>
                {v2?.metadata.mode === "historical"
                  ? "Historical workspace"
                  : v2
                    ? "Synthetic workspace"
                    : "Loading workspace"}
              </strong>{" "}
              · History reference: {v2?.metadata.reference_date || "Loading…"}.{" "}
              {v2?.metadata.mode === "historical"
                ? "Source extract, not live quotations or orders."
                : v2
                  ? "Generated demo data; not historical evidence."
                  : "Loading source metadata."}
            </span>
            <span className="preview-tag">UI preview</span>
          </div>
          <div className="page-content">
            {v2 ? (
              <IntegratedWorkspace />
            ) : (
              <div className="card">
                <p role={v2Error ? "alert" : "status"}>
                  {v2Error || "Loading snapshot and analytics…"}
                </p>
              </div>
            )}
          </div>
          <footer className="workspace-footer">
            Built for better customer conversations.
            <span>PeCal Pulse · Challenge 02 · Prototype</span>
          </footer>
        </main>
        <SalesAssistant />
        {notice && (
          <div className="toast" role="status">
            <Check size={16} />
            {notice}
            <button
              aria-label="Dismiss notification"
              onClick={() => set({ notice: "" })}
            >
              <X size={14} />
            </button>
          </div>
        )}
      </div>
    </SalesAssistantProvider>
  );
}
