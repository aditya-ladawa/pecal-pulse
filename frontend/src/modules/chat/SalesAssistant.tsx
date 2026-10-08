"use client";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import {
  AssistantRuntimeProvider,
  useExternalStoreRuntime,
  ThreadPrimitive,
  MessagePrimitive,
  ActionBarPrimitive,
  AuiIf,
  useAuiState,
  type ThreadMessageLike,
} from "@assistant-ui/react";
import {
  ArrowDown,
  Copy,
  Sparkles,
  X,
  CheckCheck,
  ChartColumn,
  Maximize2,
  Minimize2,
  Plus,
  ArrowLeftRight,
} from "lucide-react";
import { filterCustomers, useSalesStore } from "@/modules/sales/store";
import { streamChat, getChatStatus, getChatHistory } from "@/modules/sales/api";
import { dispatchEvent } from "@/core/events/router";
import { ArtifactChart } from "@/modules/artifacts/Chart";
import { ChatParts } from "./ChatParts";
import { VoicePanel } from "./VoicePanel";
import { integratedSnapshot } from "@/modules/sales/IntegratedWorkspace";
import { dashboardSnapshot } from "@/modules/sales/page-context";
import type { Page, WorkspaceContext, ChatMessage } from "@/types/sales";
export function SalesAssistantProvider({ children }: { children: ReactNode }) {
  const messages = useSalesStore((s) => s.messages),
    apiStatus = useSalesStore((s) => s.apiStatus),
    pathname = usePathname(),
    chatStatus = useSalesStore((s) => s.chatStatus),
    chatLoading = useSalesStore((s) => s.chatLoading);
  useEffect(() => {
    let alive = true;
    const saved = localStorage.getItem("pecal-chat-thread");
    const threadId = saved && /^[0-9a-f-]{36}$/i.test(saved) ? saved : null;
    useSalesStore.getState().set({ threadId });
    Promise.all([
      getChatStatus(),
      threadId ? getChatHistory(threadId) : Promise.resolve(null),
    ])
      .then(([status, history]) => {
        if (alive)
          useSalesStore
            .getState()
            .set({ chatStatus: status, messages: history?.items ?? [] });
      })
      .catch(() => {
        if (alive)
          useSalesStore.getState().set({
            notice:
              "Could not restore the assistant. Reload after the backend is ready.",
          });
      })
      .finally(() => {
        if (alive) useSalesStore.getState().set({ chatLoading: false });
      });
    return () => {
      alive = false;
    };
  }, []);
  const [running, setRunning] = useState(false),
    controller = useRef<AbortController | null>(null);
  const runtime = useExternalStoreRuntime({
    messages,
    convertMessage: (m): ThreadMessageLike => ({
      id: m.id,
      role: m.role,
      content: m.content ?? [{ type: "text", text: m.text }],
      ...(m.role === "assistant"
        ? { status: m.status ?? { type: "complete", reason: "stop" } }
        : {}),
    }),
    isRunning: running,
    isDisabled:
      apiStatus !== "connected" || chatLoading || !chatStatus?.configured,
    onNew: async (message) => {
      const text = message.content
        .filter((c) => c.type === "text")
        .map((c) => (c.type === "text" ? c.text : ""))
        .join("\n");
      if (!text.trim()) return;
      const s = useSalesStore.getState();
      const voiceTurn = s.voiceInputPending;
      s.set({ voiceInputPending: false });
      const threadId = s.threadId || crypto.randomUUID();
      localStorage.setItem("pecal-chat-thread", threadId);
      const assistantId = crypto.randomUUID();
      const updateAssistant = (change: (m: ChatMessage) => ChatMessage) => {
        const current = useSalesStore.getState();
        current.set({
          messages: current.messages.map((m) =>
            m.id === assistantId ? change(m) : m,
          ),
        });
      };
      s.set({
        threadId,
        messages: [
          ...s.messages,
          { id: crypto.randomUUID(), role: "user", text },
          {
            id: assistantId,
            role: "assistant",
            text: "",
            content: [],
            status: { type: "running" },
          },
        ],
      });
      setRunning(true);
      const abort = new AbortController();
      const applied = new Set<string>();
      controller.current = abort;
      try {
        const page: Page =
          pathname === "/insights"
            ? "insights"
            : pathname === "/customers"
              ? "customers"
              : pathname === "/follow-ups"
                ? "follow-ups"
                : "dashboard";
        const visible = filterCustomers(s.data, s.filters);
        const context: WorkspaceContext = {
          page,
          opportunity_filters: s.opportunityFilters,
          opportunity_cluster: s.opportunityCluster,
          opportunity_model_version: s.opportunities?.model_version,
          opportunity_selection_revision: s.opportunities?.selection_revision,
          commercial_scenario: s.commercialScenario,
          customer_view: s.customerView,
          customer_offset: s.customerOffset,
          dashboard_offset: s.dashboardOffset,
          opportunity_drawer_id: s.opportunityDrawerId,
          opportunity_display_limit: s.opportunityDisplayLimit,
          current_date: new Date().toLocaleDateString("en-CA"),
          page_snapshot: s.v2
            ? integratedSnapshot(s.v2, s.v2Detail, page)
            : page === "dashboard"
              ? dashboardSnapshot(s.data)
              : undefined,
          snapshot_id: s.v2?.metadata.snapshot_id,
          customer_id: s.v2
            ? s.selectedId || null
            : page === "customers"
              ? ((visible.find((c) => c.id === s.selectedId) || visible[0])
                  ?.id ?? null)
              : s.selectedId,
          filters: s.filters,
          reference_date:
            s.v2?.metadata.reference_date || s.data.reference_date,
          visible_customer_ids: s.v2
            ? page === "customers"
              ? s.v2List?.items.map((c) => c.profile.customer_id) || []
              : page === "dashboard"
                ? s.opportunities?.items.map((a) => a.customer_id) || []
                : []
            : (page === "customers"
                ? visible
                : page === "dashboard"
                  ? [...s.data.customers]
                      .sort((a, b) => b.priority - a.priority)
                      .slice(0, s.actionLimit)
                  : []
              ).map((c) => c.id),
          action_limit: s.actionLimit,
          customer_tab: s.customerTab,
          customer_activity_view: s.customerActivityView,
          artifact_ids: s.messages
            .flatMap((m) => m.artifacts ?? [])
            .slice(-50)
            .map((a) => a.id),
        };
        await streamChat(text, context, threadId, abort.signal, (event) => {
          if (abort.signal.aborted) return;
          if (event.type === "part") {
            updateAssistant((m) => {
              const content = [...(m.content ?? [])];
              content[event.index] = event.part;
              return { ...m, content };
            });
          } else if (event.type === "delta") {
            updateAssistant((m) => {
              const content = [...(m.content ?? [])];
              const part = content[event.index];
              if (part?.type === "text" || part?.type === "reasoning")
                content[event.index] = {
                  ...part,
                  text: part.text + event.delta,
                };
              return {
                ...m,
                content,
                text: content
                  .filter((p) => p.type === "text")
                  .map((p) => p.text)
                  .join("\n"),
              };
            });
          } else if (event.type === "speech") {
            if (voiceTurn)
              useSalesStore.getState().set({
                voiceResponse: {
                  id: event.id,
                  text: event.text,
                  kind: "progress",
                },
              });
          } else if (event.type === "workspace") {
            if (!applied.has(event.event.id)) {
              applied.add(event.event.id);
              dispatchEvent(event.event);
              updateAssistant((m) => ({
                ...m,
                actions: [...(m.actions ?? []), event.event.type],
                artifacts:
                  event.event.type === "artifact.created"
                    ? [...(m.artifacts ?? []), event.event.payload]
                    : m.artifacts,
              }));
            }
          } else if (event.type === "done") {
            if (
              voiceTurn &&
              !abort.signal.aborted &&
              event.reply.message.trim()
            )
              useSalesStore.getState().set({
                voiceResponse: {
                  id: assistantId,
                  text: event.reply.message,
                  kind: "final",
                },
              });
            updateAssistant((m) => ({
              ...m,
              text: event.reply.message,
              content: event.reply.content ?? m.content,
              artifacts: event.reply.artifacts,
              status: { type: "complete", reason: "stop" },
            }));
          }
        });
      } catch (error) {
        if (!abort.signal.aborted) {
          const message =
            error instanceof Error
              ? error.message
              : "Unable to complete the request.";
          if (voiceTurn)
            useSalesStore.getState().set({
              voiceResponse: {
                id: assistantId + "-error",
                kind: "error",
                text:
                  (applied.size
                    ? "Some workspace changes were applied. "
                    : "") + message,
              },
            });
          updateAssistant((m) => ({
            ...m,
            text: m.text + "\n" + message,
            content: [...(m.content ?? []), { type: "text", text: message }],
            status: { type: "incomplete", reason: "error", error: message },
          }));
        }
      } finally {
        if (controller.current === abort) {
          controller.current = null;
          setRunning(false);
        }
      }
    },
    onCancel: async () => {
      controller.current?.abort();
      const current = useSalesStore.getState();
      current.set({
        messages: current.messages.map((m) =>
          m.status?.type === "running"
            ? { ...m, status: { type: "incomplete", reason: "cancelled" } }
            : m,
        ),
      });
      controller.current = null;
      setRunning(false);
    },
  });
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      {children}
    </AssistantRuntimeProvider>
  );
}
function UserMessage() {
  return (
    <MessagePrimitive.Root className="chat-message user-message">
      <MessagePrimitive.Parts />
    </MessagePrimitive.Root>
  );
}
function AssistantMessage() {
  const id = useAuiState((s) => s.message.id),
    record = useSalesStore((s) => s.messages.find((m) => m.id === id));
  return (
    <MessagePrimitive.Root className="chat-message assistant-message">
      <div className="assistant-mark">
        <Sparkles size={14} />
        <span>Pulse</span>
      </div>
      <ChatParts />
      {!!record?.actions?.length && (
        <div className="action-receipt">
          <CheckCheck size={13} />
          {record.actions.includes("artifact.created")
            ? "Chart created in chat"
            : "Workspace updated"}
        </div>
      )}
      {record?.artifacts?.map((a) => (
        <div className="chat-artifact" key={a.id}>
          <div>
            <ChartColumn size={14} />
            <strong>{a.title}</strong>
          </div>
          <ArtifactChart artifact={a} compact />
          <small>
            {a.source === "historical" ? "Historical observed" : "Synthetic"}{" "}
            {a.unit}
          </small>
        </div>
      ))}
      <ActionBarPrimitive.Root className="message-actions">
        <ActionBarPrimitive.Copy
          className="icon-button"
          aria-label="Copy reply"
        >
          <Copy size={13} />
        </ActionBarPrimitive.Copy>
      </ActionBarPrimitive.Root>
    </MessagePrimitive.Root>
  );
}
export function SalesAssistant() {
  const open = useSalesStore((s) => s.assistantOpen),
    expanded = useSalesStore((s) => s.assistantExpanded),
    side = useSalesStore((s) => s.assistantSide),
    voiceResetRevision = useSalesStore((s) => s.voiceResetRevision),
    set = useSalesStore((s) => s.set),
    chatLoading = useSalesStore((s) => s.chatLoading),
    running = useAuiState((s) => s.thread.isRunning);
  if (!open) return null;
  return (
    <aside
      className={`chat-drawer voice-drawer${expanded ? " expanded" : ""}${expanded && side === "left" ? " dock-left" : ""}`}
      aria-label="Sales assistant"
    >
      <div className="chat-header compact-chat-header">
        <strong>Pulse</strong>
        <div className="chat-header-actions">
          <button
            className="icon-button"
            aria-label="New conversation"
            title="New conversation"
            disabled={running || chatLoading}
            onClick={() => {
              localStorage.removeItem("pecal-chat-thread");
              set({
                threadId: null,
                messages: [],
                voiceResponse: null,
                voiceInputPending: false,
                voiceResetRevision: voiceResetRevision + 1,
              });
            }}
          >
            <Plus size={17} />
          </button>
          {expanded && (
            <button
              className="icon-button"
              aria-label={`Move assistant to ${side === "right" ? "left" : "right"}`}
              title="Move panel to other side"
              onClick={() =>
                set({ assistantSide: side === "right" ? "left" : "right" })
              }
            >
              <ArrowLeftRight size={17} />
            </button>
          )}
          <button
            className="icon-button"
            aria-label={
              expanded ? "Collapse sales assistant" : "Expand sales assistant"
            }
            title={expanded ? "Collapse panel" : "Expand panel"}
            aria-expanded={expanded}
            onClick={() => set({ assistantExpanded: !expanded })}
          >
            {expanded ? <Minimize2 size={17} /> : <Maximize2 size={17} />}
          </button>
          <button
            className="icon-button"
            aria-label="Close sales assistant"
            title="Close panel"
            onClick={() => set({ assistantOpen: false })}
          >
            <X size={17} />
          </button>
        </div>
      </div>
      <ThreadPrimitive.Root className="chat-thread">
        <VoicePanel key={voiceResetRevision} />
        <ThreadPrimitive.Viewport className="chat-viewport">
          <ThreadPrimitive.Messages>
            {({ message }) =>
              message.role === "user" ? <UserMessage /> : <AssistantMessage />
            }
          </ThreadPrimitive.Messages>
        </ThreadPrimitive.Viewport>
        <ThreadPrimitive.ScrollToBottom className="scroll-latest">
          <ArrowDown size={13} />
          Latest
        </ThreadPrimitive.ScrollToBottom>
      </ThreadPrimitive.Root>
    </aside>
  );
}
