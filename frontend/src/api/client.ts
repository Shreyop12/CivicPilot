import type { AgencyDashboard, AgencySummary, ChatResponse } from "./types";

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

export function postChat(conversationId: string, message: string): Promise<ChatResponse> {
  return request<ChatResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify({ conversation_id: conversationId, message }),
  });
}
