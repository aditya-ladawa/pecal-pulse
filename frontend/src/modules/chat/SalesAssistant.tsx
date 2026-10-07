"use client";
import { useRef, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import {
  AssistantRuntimeProvider,
  useExternalStoreRuntime,
  ThreadPrimitive,
  MessagePrimitive,
  ComposerPrimitive,
  ActionBarPrimitive,
  AuiIf,
  useAuiState,
  type ThreadMessageLike,
} from "@assistant-ui/react";
import { MarkdownTextPrimitive } from "@assistant-ui/react-markdown";
import {
  ArrowUp,
  ArrowDown,
  Copy,
  Mic,
  Sparkles,
  X,
  Square,
  CheckCheck,
  ChartColumn,
} from "lucide-react";
import { useSalesStore } from "@/modules/sales/store";
import { sendChat } from "@/modules/sales/api";
import { dispatchEvent } from "@/core/events/router";
import { ArtifactChart } from "@/modules/artifacts/Chart";
import type { Page } from "@/types/sales";
const starters = [
  "Show automotive customers",
  "Create an industry chart",
  "Prepare a conversation",
  "Open follow-ups",
];
export function SalesAssistantProvider({ children }: { children: ReactNode }) {
  const messages = useSalesStore((s) => s.messages),
    apiStatus = useSalesStore((s) => s.apiStatus),
    pathname = usePathname();
  const [running, setRunning] = useState(false),
    controller = useRef<AbortController | null>(null);
  const runtime = useExternalStoreRuntime({
    messages,
    convertMessage: (m): ThreadMessageLike => ({
      id: m.id,
      role: m.role,
      content: [{ type: "text", text: m.text }],
      ...(m.role === "assistant"
        ? { status: { type: "complete", reason: "stop" } }
        : {}),
    }),
    isRunning: running,
    isDisabled: apiStatus !== "connected",
    onNew: async (message) => {
      const text = message.content
        .filter((c) => c.type === "text")
        .map((c) => (c.type === "text" ? c.text : ""))
        .join("\n");
      if (!text.trim()) return;
      const s = useSalesStore.getState();
      s.set({
        messages: [
          ...s.messages,
          { id: crypto.randomUUID(), role: "user", text },
        ],
      });
      setRunning(true);
      const abort = new AbortController();
      controller.current = abort;
      try {
        const page: Page =
          pathname === "/customers"
            ? "customers"
            : pathname === "/follow-ups"
              ? "follow-ups"
              : "dashboard";
        const result = await sendChat(
          text,
          { page, customer_id: s.selectedId, filters: s.filters },
          abort.signal,
        );
        if (abort.signal.aborted) return;
        result.events.forEach(dispatchEvent);
        const current = useSalesStore.getState();
        current.set({
          messages: [
            ...current.messages,
            {
              id: crypto.randomUUID(),
              role: "assistant",
              text: result.message,
              artifacts: result.artifacts,
              actions: result.events.map((e) => e.type),
            },
          ],
        });
      } catch (error) {
        if (!abort.signal.aborted) {
          const current = useSalesStore.getState();
          current.set({
            messages: [
              ...current.messages,
              {
                id: crypto.randomUUID(),
                role: "assistant",
                text:
                  error instanceof Error
                    ? error.message
                    : "Unable to complete the request.",
              },
            ],
          });
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
      <MessagePrimitive.Parts
        components={{
          Text: () => <MarkdownTextPrimitive className="markdown" />,
        }}
      />
      {!!record?.actions?.length && (
        <div className="action-receipt">
          <CheckCheck size={13} />
          {record.actions.includes("artifact.created")
            ? "Chart added to workspace"
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
          <small>Synthetic {a.unit} · also on Dashboard</small>
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
    set = useSalesStore((s) => s.set),
    status = useSalesStore((s) => s.apiStatus);
  if (!open)
    return (
      <button
        className="chat-launcher"
        onClick={() => set({ assistantOpen: true })}
        aria-label="Open sales assistant"
      >
        <Sparkles size={21} />
        <span>Ask Pulse</span>
      </button>
    );
  return (
    <aside className="chat-drawer" aria-label="Sales assistant">
      <div className="chat-header">
        <span className="chat-orb">
          <Sparkles size={23} />
        </span>
        <div>
          <strong>Your sales assistant</strong>
          <small>Pulse · assistant-ui preview</small>
        </div>
        <button
          className="icon-button"
          aria-label="Close sales assistant"
          onClick={() => set({ assistantOpen: false })}
        >
          <X size={19} />
        </button>
      </div>
      <div className="chat-context">
        <span className="status-dot" />
        Scripted mock · workspace actions enabled
      </div>
      <ThreadPrimitive.Root className="chat-thread">
        <ThreadPrimitive.Viewport className="chat-viewport">
          <AuiIf condition={(s) => s.thread.isEmpty && !s.thread.isRunning}>
            <div className="chat-welcome">
              <div className="welcome-spark">
                <Sparkles size={28} />
              </div>
              <h2>
                A little help with
                <br />
                your next conversation.
              </h2>
              <p>Find an account, explore its evidence, or create a chart.</p>
              <div className="suggestions">
                {starters.map((prompt) => (
                  <ThreadPrimitive.Suggestion
                    key={prompt}
                    prompt={prompt}
                    send
                    className="suggestion"
                  >
                    {prompt}
                    <ArrowUp size={13} />
                  </ThreadPrimitive.Suggestion>
                ))}
              </div>
              <small>
                This preview uses synthetic data and scripted replies. No
                language model is connected yet.
              </small>
            </div>
          </AuiIf>
          <ThreadPrimitive.Messages>
            {({ message }) =>
              message.role === "user" ? <UserMessage /> : <AssistantMessage />
            }
          </ThreadPrimitive.Messages>
          <AuiIf condition={(s) => s.thread.isRunning}>
            <div className="thinking">
              <i />
              <i />
              <i />
              <span>Working on your request…</span>
            </div>
          </AuiIf>
        </ThreadPrimitive.Viewport>
        <ThreadPrimitive.ScrollToBottom className="scroll-latest">
          <ArrowDown size={13} /> Latest
        </ThreadPrimitive.ScrollToBottom>
        <div className="composer-wrap">
          <ComposerPrimitive.Root className="composer">
            <ComposerPrimitive.Input
              aria-label="Message sales assistant"
              placeholder={
                status === "connected"
                  ? "Ask about customers, or try a prompt…"
                  : "Backend offline — reconnect to chat"
              }
              rows={2}
            />
            <div className="composer-bottom">
              <button
                disabled
                className="icon-button"
                aria-label="Voice input unavailable in mock"
                title="Voice will be connected later"
              >
                <Mic size={18} />
              </button>
              <span>Sales workspace context included</span>
              <AuiIf condition={(s) => !s.thread.isRunning}>
                <ComposerPrimitive.Send
                  className="send-button"
                  aria-label="Send message"
                >
                  <ArrowUp size={18} />
                </ComposerPrimitive.Send>
              </AuiIf>
              <AuiIf condition={(s) => s.thread.isRunning}>
                <ComposerPrimitive.Cancel
                  className="send-button"
                  aria-label="Stop response"
                >
                  <Square size={14} />
                </ComposerPrimitive.Cancel>
              </AuiIf>
            </div>
          </ComposerPrimitive.Root>
          <div className="composer-note">
            Mock suggestions need your review.
          </div>
        </div>
      </ThreadPrimitive.Root>
    </aside>
  );
}
