const BASE = "/evidence-api";

export async function evidenceApi(path: string, signal?: AbortSignal): Promise<unknown> {
  const response = await fetch(`${BASE}${path}`, { signal });
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = (body as { error?: unknown } | null)?.error;
    throw new Error(typeof detail === "string" ? detail : `Request failed (${response.status})`);
  }
  return body;
}

export const exportCsvUrl = (query: string) => `${BASE}/export.csv${query}`;
