import { useEffect, useState } from "react";

import { EmptyState } from "@/components/status/EmptyState";
import { Button } from "@/components/ui/button";
import { api, type PredictionHistoryItem } from "@/lib/api";
import { classLabel, formatProbability, formatTimestamp } from "@/lib/format";
import { History } from "lucide-react";

type HistoryState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; records: PredictionHistoryItem[] };

export function HistoryPage() {
  const [attempt, setAttempt] = useState(0);
  const [seenAttempt, setSeenAttempt] = useState(0);
  const [state, setState] = useState<HistoryState>({ status: "loading" });
  if (seenAttempt !== attempt) {
    setSeenAttempt(attempt);
    setState({ status: "loading" });
  }

  useEffect(() => {
    let cancelled = false;
    api
      .history()
      .then((body) => {
        if (!cancelled) {
          setState({ status: "ready", records: body.predictions });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState({
            status: "error",
            message: error instanceof Error ? error.message : "Prediction history is unavailable.",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-3xl">
          <p className="text-xs font-medium tracking-wide text-muted uppercase">History</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight">Prediction history</h1>
          <p className="mt-4 text-sm leading-6 text-muted">
            Stored scores from the API, oldest first. The browser does not keep a separate history.
          </p>
        </div>
        <Button type="button" variant="secondary" onClick={() => setAttempt((value) => value + 1)}>
          Refresh
        </Button>
      </header>
      {state.status === "loading" ? <p role="status">Loading history.</p> : null}
      {state.status === "error" ? (
        <p role="alert" className="text-sm leading-6">
          {state.message}
        </p>
      ) : null}
      {state.status === "ready" && state.records.length === 0 ? (
        <EmptyState
          icon={History}
          title="No stored predictions"
          body="Score a reported collision. A successful response is saved by the API and will appear here."
        />
      ) : null}
      {state.status === "ready" && state.records.length > 0 ? <HistoryTable records={state.records} /> : null}
    </div>
  );
}

function HistoryTable({ records }: { records: PredictionHistoryItem[] }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-white">
      <table className="min-w-full text-left text-sm">
        <caption className="sr-only">Stored prediction responses</caption>
        <thead className="border-b border-line text-xs text-muted">
          <tr>
            <th className="px-4 py-3 font-medium">Record</th>
            <th className="px-4 py-3 font-medium">Time (UTC)</th>
            <th className="px-4 py-3 font-medium">Probability</th>
            <th className="px-4 py-3 font-medium">Class</th>
            <th className="px-4 py-3 font-medium">Band</th>
          </tr>
        </thead>
        <tbody>
          {records.map((record) => (
            <tr key={record.id} className="border-b border-line last:border-0">
              <td className="px-4 py-3 font-medium">{record.id}</td>
              <td className="px-4 py-3">{formatTimestamp(record.created_at)}</td>
              <td className="px-4 py-3">{formatProbability(record.probability)}</td>
              <td className="px-4 py-3">{classLabel(record.predicted_class_label)}</td>
              <td className="px-4 py-3">{record.risk_level}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
