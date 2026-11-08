const BASE = "/sandbox-api";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public body: unknown,
  ) {
    super(message);
  }
}

export async function api(path: string, options: { method?: string; body?: unknown; signal?: AbortSignal } = {}): Promise<unknown> {
  const response = await fetch(`${BASE}${path}`, {
    method: options.method ?? "GET",
    headers: options.body === undefined ? undefined : { "content-type": "application/json" },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal,
  });
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = (body as { error?: unknown } | null)?.error;
    throw new ApiError(response.status, typeof detail === "string" ? detail : `Request failed (${response.status})`, body);
  }
  return body;
}

export const markersCsvUrl = (runId: string) => `${BASE}/runs/${encodeURIComponent(runId)}/markers.csv`;

export interface RunRequest {
  limit: number;
  channels: string[];
  methods: string[];
  sources: string[];
  models: string[];
  lanes: number;
  window_turns: number;
}

export interface RescoreRequest {
  dangerous_threshold: number;
  uncertain_threshold: number;
  require_hard_flag: boolean;
}
