import type { AgencyDashboard, AgencySummary, ChatStreamEvent } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    throw new Error(`Request to ${path} failed with status ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function fetchAgencies(): Promise<AgencySummary[]> {
  return request<AgencySummary[]>("/api/agencies");
}

export function fetchDashboard(toptierCode: string): Promise<AgencyDashboard> {
  return request<AgencyDashboard>(`/api/agencies/${toptierCode}/dashboard`);
}

export async function streamChat(
  conversationId: string,
  message: string,
  onEvent: (event: ChatStreamEvent) => void,
): Promise<void> {
  const response = await fetch(`${API_BASE}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conversation_id: conversationId, message }),
  });
  if (!response.ok || !response.body) {
    throw new Error(`Request to /api/chat/stream failed with status ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";
    for (const rawEvent of events) {
      const dataLine = rawEvent.split("\n").find((line) => line.startsWith("data: "));
      if (dataLine) {
        onEvent(JSON.parse(dataLine.slice("data: ".length)) as ChatStreamEvent);
      }
    }
  }
}
