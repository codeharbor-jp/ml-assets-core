const BASE_URL =
  process.env.NEXT_PUBLIC_CORE_API_URL ?? "http://localhost:8000/api/v1";

export type MetricRow = {
  metric: string;
  value: number;
};

export type MetricsResponse = {
  generated_at: string;
  data: MetricRow[];
  meta: Record<string, string>;
};

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    cache: "no-store",
    ...init,
  });
  if (!res.ok) {
    throw new Error(`Analytics API error: ${res.status}`);
  }
  return (await res.json()) as T;
}

export function fetchModelMetrics(): Promise<MetricsResponse> {
  return fetchJson("/metrics/model");
}

export function fetchTradingMetrics(pairId?: string): Promise<MetricsResponse> {
  const query = pairId ? `?pair_id=${encodeURIComponent(pairId)}` : "";
  return fetchJson(`/metrics/trading${query}`);
}

export function fetchDataQualityMetrics(): Promise<MetricsResponse> {
  return fetchJson("/metrics/data-quality");
}

export function fetchRiskMetrics(): Promise<MetricsResponse> {
  return fetchJson("/metrics/risk");
}

