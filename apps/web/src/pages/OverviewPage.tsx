import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { targetStatement } from "@/content/status";
import { api, type HealthResponse, type ModelResponse } from "@/lib/api";
import { shortVersion } from "@/lib/format";

type OverviewState =
  | { status: "loading" }
  | { status: "unavailable"; message: string }
  | { status: "ready"; health: HealthResponse; model: ModelResponse | null; modelError: string | null };

export function OverviewPage() {
  const [attempt, setAttempt] = useState(0);
  const [seenAttempt, setSeenAttempt] = useState(0);
  const [state, setState] = useState<OverviewState>({ status: "loading" });
  if (seenAttempt !== attempt) {
    setSeenAttempt(attempt);
    setState({ status: "loading" });
  }

  useEffect(() => {
    let cancelled = false;
    api
      .health()
      .then(async (health) => {
        if (!health.ready) {
          if (!cancelled) {
            setState({ status: "ready", health, model: null, modelError: null });
          }
          return;
        }
        try {
          const model = await api.model();
          if (!cancelled) {
            setState({ status: "ready", health, model, modelError: null });
          }
        } catch (error) {
          if (!cancelled) {
            setState({
              status: "ready",
              health,
              model: null,
              modelError: error instanceof Error ? error.message : "Model information is unavailable.",
            });
          }
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState({
            status: "unavailable",
            message: error instanceof Error ? error.message : "The RoadRisk API is not reachable.",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  return (
    <div className="space-y-8">
      <header className="max-w-3xl">
        <p className="text-xs font-medium tracking-wide text-muted uppercase">Overview</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">RoadRisk</h1>
        <p className="mt-4 text-base leading-7 text-navy">{targetStatement}</p>
      </header>
      <ServiceStatus state={state} onRetry={() => setAttempt((value) => value + 1)} />
      <section className="grid gap-4 md:grid-cols-2">
        <Card>
          <h2 className="text-sm font-medium text-muted">Next step</h2>
          <p className="mt-3 text-sm leading-6">
            Submit one reported collision on the prediction page. The result is the API response:
            a calibrated probability, a binary class, and a model-score band.
          </p>
          <Link
            to="/predict"
            className="mt-4 inline-flex rounded-md bg-navy px-4 py-2 text-sm font-medium text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy"
          >
            Open prediction
          </Link>
        </Card>
        <Card>
          <h2 className="text-sm font-medium text-muted">What this is not</h2>
          <p className="mt-3 text-sm leading-6">
            Risk bands are categories of the model score. They are not safety grades, and they are
            not exposure-adjusted collision rates. The model does not estimate whether a collision
            will occur.
          </p>
        </Card>
      </section>
    </div>
  );
}

function ServiceStatus({ state, onRetry }: { state: OverviewState; onRetry: () => void }) {
  if (state.status === "loading") {
    return <p role="status">Checking the API.</p>;
  }
  if (state.status === "unavailable") {
    return (
      <Card>
        <h2 className="text-sm font-medium text-muted">API</h2>
        <p className="mt-3 text-sm font-medium" role="alert">
          Unavailable
        </p>
        <p className="mt-2 text-sm leading-6">{state.message}</p>
        <Button className="mt-4" type="button" variant="secondary" onClick={onRetry}>
          Retry
        </Button>
      </Card>
    );
  }
  const ready = state.health.ready;
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card>
        <h2 className="text-sm font-medium text-muted">API</h2>
        <p className="mt-3 text-sm font-medium">{ready ? "Ready" : "Not ready"}</p>
        <p className="mt-2 text-sm leading-6 text-muted">
          {state.health.detail ?? "The health check completed."}
        </p>
      </Card>
      <Card>
        <h2 className="text-sm font-medium text-muted">Loaded model</h2>
        {state.model ? (
          <>
            <p className="mt-3 font-mono text-sm" title={state.model.model_version}>
              {shortVersion(state.model.model_version)}
            </p>
            <p className="mt-2 text-sm leading-6 text-muted">
              {state.model.model}, {state.model.artifact_role}. Threshold {state.model.binary_threshold}.
            </p>
          </>
        ) : (
          <p className="mt-3 text-sm leading-6" role="status">
            {state.modelError ?? "The model is not loaded, so model information is not shown."}
          </p>
        )}
      </Card>
    </div>
  );
}
