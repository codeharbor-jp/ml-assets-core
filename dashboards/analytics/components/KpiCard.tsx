"use client";

import React from "react";

type Props = {
  title: string;
  value: string;
  description?: string;
};

export function KpiCard({ title, value, description }: Props) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-slate-500">{title}</h3>
      <p className="mt-2 text-2xl font-bold text-slate-900">{value}</p>
      {description ? (
        <p className="mt-1 text-xs text-slate-500">{description}</p>
      ) : null}
    </div>
  );
}

