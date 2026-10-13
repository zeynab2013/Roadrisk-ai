import { useEffect, useState } from "react";
import { MapPinned } from "lucide-react";

import { EmptyState } from "@/components/status/EmptyState";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api, type AreaSummaryResponse } from "@/lib/api";
import { formatCount, formatProbability } from "@/lib/format";

type AreaState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; summary: AreaSummaryResponse };

export function AreasPage() {
  const [attempt, setAttempt] = useState(0);
  const [seenAttempt, setSeenAttempt] = useState(0);
  const [state, setState] = useState<AreaState>({ status: "loading" });
  if (seenAttempt !== attempt) {
    setSeenAttempt(attempt);
    setState({ status: "loading" });
  }

  useEffect(() => {
    let cancelled = false;
    api
      .areaSummary()
      .then((summary) => {
        if (!cancelled) {
          setState({ status: "ready", summary });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState({
            status: "error",
            message: error instanceof Error ? error.message : "Area summary is not available.",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  return (
    <div className="space-y-6">
      <header className="max-w-3xl">
        <p className="text-xs font-medium tracking-wide text-muted uppercase">Areas</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">Area summary</h1>
        <p className="mt-4 text-sm leading-6 text-muted">
          Shares of model-score bands among recorded collisions, grouped by urban or rural area.
          This is not a ranking of places as safe or unsafe.
        </p>
      </header>
      {state.status === "loading" ? <p role="status">Loading the area summary.</p> : null}
      {state.status === "error" ? (
        <Card>
          <p role="alert" className="text-sm leading-6">
            {state.message}
          </p>
          <Button className="mt-4" type="button" variant="secondary" onClick={() => setAttempt((value) => value + 1)}>
            Retry
          </Button>
        </Card>
      ) : null}
      {state.status === "ready" && state.summary.groups.length === 0 ? (
        <EmptyState icon={MapPinned} title="No groups in the summary" body="The saved summary did not include any area groups." />
      ) : null}
      {state.status === "ready" && state.summary.groups.length > 0 ? <AreaDetails summary={state.summary} /> : null}
    </div>
  );
}

function AreaDetails({ summary }: { summary: AreaSummaryResponse }) {
  const supported = new Set(summary.supported_groups.map((group) => group.area_id));
  return (
    <div className="space-y-4">
      <Card>
        <p className="text-sm leading-6">{summary.grouping_reason}</p>
        <p className="mt-2 text-sm leading-6">{summary.not_estimated}</p>
        <p className="mt-2 text-sm leading-6">{summary.limitation}</p>
        <p className="mt-2 text-sm leading-6 text-muted">
          Population: {summary.population} Recorded rows: {formatCount(summary.rows)}. Minimum
          support: {formatCount(summary.minimum_support)}. Groups below that count are listed, but
          they are not treated as a supported comparison.
        </p>
      </Card>
      <div className="overflow-x-auto rounded-xl border border-line bg-white">
        <table className="min-w-full text-left text-sm">
          <caption className="sr-only">Model-score shares by urban or rural area</caption>
          <thead className="border-b border-line text-xs text-muted">
            <tr>
              <th className="px-4 py-3 font-medium">Area</th>
              <th className="px-4 py-3 font-medium">Recorded collisions</th>
              <th className="px-4 py-3 font-medium">Mean score</th>
              <th className="px-4 py-3 font-medium">Support</th>
            </tr>
          </thead>
          <tbody>
            {summary.groups.map((group) => (
              <tr key={group.area_id} className="border-b border-line last:border-0">
                <td className="px-4 py-3 font-medium">{group.label}</td>
                <td className="px-4 py-3">{formatCount(group.collisions)}</td>
                <td className="px-4 py-3">
                  {group.mean_predicted_probability === null
                    ? "—"
                    : formatProbability(group.mean_predicted_probability)}
                </td>
                <td className="px-4 py-3">{supported.has(group.area_id) ? "Meets minimum" : "Below minimum"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
