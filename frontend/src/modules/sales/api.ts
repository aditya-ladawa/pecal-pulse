import type {
  ChatReply,
  CustomerFilters,
  EventEnvelope,
  Page,
  Workspace,
} from "@/types/sales";
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/sales/${path}`, init);
  if (!response.ok)
    throw new Error(
      "The local backend could not complete this action. Please try again.",
    );
  return response.json() as Promise<T>;
}
export const loadWorkspace = () => request<Workspace>("bootstrap");
export const sendChat = (
  message: string,
  context: { page: Page; customer_id: string; filters: CustomerFilters },
  signal: AbortSignal,
) =>
  request<ChatReply>("chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, context }),
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
