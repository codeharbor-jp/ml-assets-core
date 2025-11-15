"use client";

import React, { useMemo } from "react";
import useSWR from "swr";
import {
  fetchDataQualityMetrics,
  fetchModelMetrics,
  fetchRiskMetrics,
  fetchTradingMetrics,
} from "../lib/api";
import { KpiCard } from "../components/KpiCard";

function formatValue(value: number): string {
  if (Number.isNaN(value)) return "-";
  if (Math.abs(value) >= 1000) {
    return `${(value / 1000).toFixed(1)}k`;
  }
  return value.toFixed(2);
}

export default function DashboardPage(): JSX.Element {
  const { data: modelMetrics } = useSWR("/metrics/model", fetchModelMetrics, {
    refreshInterval: 30000,
  });
  const { data: tradingMetrics } = useSWR(
    "/metrics/trading",
    () => fetchTradingMetrics(),
    { refreshInterval: 45000 },
  );
  const { data: dataQualityMetrics } = useSWR(
    "/metrics/data-quality",
    fetchDataQualityMetrics,
    { refreshInterval: 60000 },
  );
  const { data: riskMetrics } = useSWR(
    "/metrics/risk",
    fetchRiskMetrics,
    { refreshInterval: 60000 },
  );

  const kpis = useMemo(() => {
    const items: { title: string; value: string; description?: string }[] = [];
    if (modelMetrics) {
      modelMetrics.data.forEach((row) => {
        items.push({
          title: `Model · ${row.metric}`,
          value: formatValue(row.value),
        });
      });
    }
    if (tradingMetrics) {
      tradingMetrics.data.forEach((row) => {
        items.push({
          title: `Trading · ${row.metric}`,
          value: formatValue(row.value),
        });
      });
    }
    if (dataQualityMetrics) {
      dataQualityMetrics.data.forEach((row) => {
        items.push({
          title: `DQ · ${row.metric}`,
          value: formatValue(row.value),
        });
      });
    }
    if (riskMetrics) {
      riskMetrics.data.forEach((row) => {
        items.push({
          title: `Risk · ${row.metric}`,
          value: formatValue(row.value),
        });
      });
    }
    return items.slice(0, 8);
  }, [modelMetrics, tradingMetrics, dataQualityMetrics, riskMetrics]);

  return (
    <main className="mx-auto flex min-h-screen max-w-6xl flex-col gap-6 p-6">
      <header>
        <h1 className="text-3xl font-bold text-slate-900">
          ml-assets-core Analytics
        </h1>
        <p className="mt-2 text-sm text-slate-500">
          Prefect flows, trading performance, data quality, and risk monitoring
          KPIs. Updated every 30–60 seconds.
        </p>
      </header>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {kpis.map((item) => (
          <KpiCard
            key={`${item.title}-${item.value}`}
            title={item.title}
            value={item.value}
            description={item.description}
          />
        ))}
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-lg font-semibold text-slate-700">
          Notes for engineers
        </h2>
        <ul className="mt-2 space-y-1 text-sm text-slate-500">
          <li>
            - 接続先は `NEXT_PUBLIC_CORE_API_URL` で切り替え可能です。Prefect
            Work Pool のエンドポイントに合わせて設定してください。
          </li>
          <li>
            - 実運用では AuthN/AuthZ を加え、指標ごとにチャート (e.g. Recharts,
            nivo) を追加することを推奨します。
          </li>
          <li>
            - ここで使用しているメトリクスは `GET /metrics/*` の API
            レスポンスから直接描画しています。
          </li>
        </ul>
      </section>
    </main>
  );
}

