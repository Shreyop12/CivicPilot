import { useEffect, useState } from "react";
import { Bar, BarChart, Cell, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { fetchDashboard } from "../api/client";
import type { AgencyDashboard } from "../api/types";
import { buildChartData } from "./chartData";
import { CitationStamp } from "./CitationStamp";
import { Button } from "./ui/button";

export interface AgencyRecordProps {
  toptierCode: string;
}

type LoadState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; dashboard: AgencyDashboard };

export function AgencyRecord({ toptierCode }: AgencyRecordProps) {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    fetchDashboard(toptierCode)
      .then((dashboard) => {
        if (!cancelled) setState({ status: "ready", dashboard });
      })
      .catch(() => {
        if (!cancelled) setState({ status: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, [toptierCode, retryCount]);

  if (state.status === "loading") {
    return <div className="p-6 text-sm text-muted">Loading…</div>;
  }

  if (state.status === "error") {
    return (
      <div className="p-6 text-sm text-muted">
        <p>Couldn't load this agency's data.</p>
        <Button variant="outline" size="sm" className="mt-2" onClick={() => setRetryCount((c) => c + 1)}>
          Retry
        </Button>
      </div>
    );
  }

  const { dashboard } = state;
  const chartData = buildChartData(dashboard.obligations);

  return (
    <div className="p-6">
      <div className="font-mono text-[10px] uppercase tracking-wider text-muted">Agency record</div>
      <h1 className="mt-1 font-serif text-2xl font-medium text-ink">{dashboard.name}</h1>
      <div className="font-mono text-[11px] tracking-wide text-muted">
        TOPTIER {dashboard.toptier_code}
        {dashboard.fr_slug ? ` · FR SLUG ${dashboard.fr_slug}` : ""}
      </div>

      <h2 className="mt-6 border-b border-hairline pb-1.5 text-xs uppercase tracking-wider text-muted">
        Obligations by fiscal year
      </h2>
      {dashboard.obligations.length === 0 ? (
        <p className="mt-3 text-sm text-muted">No obligation data available for this agency.</p>
      ) : (
        <ResponsiveContainer width="100%" height={160}>
          <BarChart data={chartData}>
            <XAxis dataKey="fiscalYear" fontSize={10} />
            <YAxis hide />
            <Bar dataKey="amount" radius={[2, 2, 0, 0]}>
              {chartData.map((point) => (
                <Cell key={point.fiscalYear} fill="#1D2A54" fillOpacity={point.partial ? 0.6 : 1} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}

      <h2 className="mt-6 border-b border-hairline pb-1.5 text-xs uppercase tracking-wider text-muted">
        Final rules — last 12 months
      </h2>
      {dashboard.rules.length === 0 ? (
        <p className="mt-3 text-sm text-muted">No final rules issued in the last 12 months.</p>
      ) : (
        <ul>
          {dashboard.rules.map((rule) => (
            <li key={rule.document_number} className="flex items-baseline gap-3.5 border-t border-hairline py-2.5 text-sm">
              <span className="w-24 shrink-0 font-mono text-ink">{rule.document_number}</span>
              <span className="flex-1 text-ink">{rule.title}</span>
              <span className="w-20 shrink-0 text-right font-mono text-[11px] text-muted">{rule.publication_date}</span>
              <CitationStamp label={`doc:${rule.document_number}`} variant="verified" href={rule.html_url} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
