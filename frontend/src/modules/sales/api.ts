import { createParser } from "eventsource-parser";
import type {
  ChatReply,
  CustomerFilters,
  EventEnvelope,
  Page,
  Workspace,
  WorkspaceContext,
  ChatStatus,
  ChatMessage,
  ChatPart,
} from "@/types/sales";
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/sales/${path}`, init);
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      typeof error?.detail === "string"
        ? error.detail
        : "The local backend could not complete this action. Please try again.",
    );
  }
  return response.json() as Promise<T>;
}
export const loadWorkspace = () => request<Workspace>("bootstrap");
export const sendChat = (
  message: string,
  context: WorkspaceContext,
  threadId: string,
  signal: AbortSignal,
) =>
  request<ChatReply>("chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, context, thread_id: threadId }),
    signal,
  });
export const saveFollowup = (payload: {
  customer_id: string;
  owner: string;
  due_date: string;
  note: string;
  outcome: string;
}) =>
  request<EventEnvelope>("followups", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
export const setFollowupStatus = (id: string, status: "open" | "done") =>
  request<EventEnvelope>(`followups/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });

export const getChatStatus = () => request<ChatStatus>("chat/status");
export const getChatHistory = (threadId: string) =>
  request<{ thread_id: string; items: ChatMessage[] }>(
    `chat/threads/${threadId}/messages`,
  );

export type ChatStreamEvent =
  | { type: "start"; thread_id: string; message_id: string }
  | { type: "part"; index: number; part: ChatPart }
  | { type: "delta"; index: number; delta: string }
  | { type: "workspace"; event: EventEnvelope }
  | { type: "done"; reply: ChatReply }
  | { type: "error"; message: string };

export async function streamChat(
  message: string,
  context: WorkspaceContext,
  threadId: string,
  signal: AbortSignal,
  onEvent: (event: ChatStreamEvent) => void,
) {
  const response = await fetch("/api/sales/chat/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({ message, context, thread_id: threadId }),
    signal,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      typeof error?.detail === "string"
        ? error.detail
        : "Unable to start the assistant stream.",
    );
  }
  if (!response.body) throw new Error("No response stream was returned.");
  let finished = false;
  let streamError: string | null = null;
  const parser = createParser({
    onEvent: ({ data }) => {
      const event: ChatStreamEvent = JSON.parse(data);
      if (event.type === "done") finished = true;
      if (event.type === "error") streamError = event.message;
      else onEvent(event);
    },
  });
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      parser.feed(decoder.decode(value, { stream: true }));
    }
    parser.feed(decoder.decode());
    if (streamError) throw new Error(streamError);
    if (!finished && !signal.aborted)
      throw new Error("The response stream was interrupted. Please retry.");
  } finally {
    reader.releaseLock();
  }
}

export const getV2Bootstrap = () =>
  request<import("@/types/sales-v2").Bootstrap>("v2/bootstrap");
export function getV2Customers(
  snapshot: string,
  filters: CustomerFilters,
  offset = 0,
) {
  const query = new URLSearchParams({
    snapshot_id: snapshot,
    sort: "priority",
    limit: "20",
    offset: String(offset),
  });
  if (filters.industry !== "all") query.set("industry_id", filters.industry);
  if (filters.segment !== "all") query.set("segment_id", filters.segment);
  if (filters.action !== "all") query.set("action", filters.action);
  if (filters.query) query.set("query", filters.query);
  return request<import("@/types/sales-v2").CustomerList>(
    `v2/customers?${query}`,
  );
}
export const getV2Detail = (
  snapshot: string,
  customer: string,
  filters?: import("@/types/opportunities").OpportunityFilters,
) =>
  request<import("@/types/sales-v2").Detail>(
    `v2/customers/${encodeURIComponent(customer)}?snapshot_id=${encodeURIComponent(snapshot)}${filters ? `&window_days=${filters.window_days}&include_past_due=${filters.include_past_due}&include_inferred=${filters.include_inferred}` : ""}`,
  );
export const getV2Followups = (snapshot: string) =>
  request<{ items: import("@/types/sales").Followup[] }>(
    `v2/followups?snapshot_id=${encodeURIComponent(snapshot)}`,
  );
export const patchV2Workflow = (
  snapshot: string,
  customer: string,
  payload: unknown,
) =>
  request(
    `v2/customers/${encodeURIComponent(customer)}/workflow?snapshot_id=${encodeURIComponent(snapshot)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
