"use client";
import { useEffect, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  UsersRound,
  ChartNoAxesCombined,
  Sparkles,
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
  { href: "/insights", label: "Insights", icon: ChartNoAxesCombined },
];
export function AppShell({ children }: { children: ReactNode }) {
  const v2 = useSalesStore((s) => s.v2),
    v2Error = useSalesStore((s) => s.v2Error);
  const pathname = usePathname(),
    router = useRouter(),
    assistantOpen = useSalesStore((s) => s.assistantOpen),
    request = useSalesStore((s) => s.requestedPage),
    notice = useSalesStore((s) => s.notice),
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
        className={`app-shell horizontal-shell ${assistantOpen ? "assistant-open" : ""}`}
      >
        <header className="workspace-topnav">
          <Link href="/" className="brand" aria-label="PeCal Pulse dashboard">
            <span className="brand-icon">
              p<span />
            </span>
            <span className="brand-name">
              PeCal<span>pulse</span>
            </span>
          </Link>
          <nav aria-label="Main navigation">
            {nav.map((n) => (
              <Link
                key={n.href}
                href={n.href}
                className={`nav-link ${pathname === n.href || (n.href === "/customers" && pathname === "/follow-ups") ? "active" : ""}`}
                aria-current={pathname === n.href ? "page" : undefined}
              >
                <n.icon size={18} />
                <span>{n.label}</span>
                {n.href === "/follow-ups" && v2 && openTasks > 0 && (
                  <i>{openTasks}</i>
                )}
              </Link>
            ))}
          </nav>
          <button
            className="topnav-assistant"
            onClick={() => set({ assistantOpen: !assistantOpen })}
            aria-label="Toggle sales assistant"
            aria-expanded={assistantOpen}
          >
            <Sparkles size={17} />
            <span>Ask Pulse</span>
          </button>
        </header>
        <main className="main">
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
