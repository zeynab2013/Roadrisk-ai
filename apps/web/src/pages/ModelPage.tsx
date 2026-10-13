import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api, type HealthResponse, type ModelResponse } from "@/lib/api";

type ModelState =
  | { status: "loading" }
  | { status: "unavailable"; message: string }
  | { status: "not-ready"; health: HealthResponse }
  | { status: "ready"; health: HealthResponse; model: ModelResponse };

export function ModelPage() {
  const [attempt, setAttempt] = useState(0);
  const [seenAttempt, setSeenAttempt] = useState(0);
  const [state, setState] = useState<ModelState>({ status: "loading" });
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
            setState({ status: "not-ready", health });
          }
          return;
        }
        const model = await api.model();
        if (!cancelled) {
          setState({ status: "ready", health, model });
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
    <div className="space-y-6">
      <header className="max-w-3xl">
        <p className="text-xs font-medium tracking-wide text-muted uppercase">Model</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">Model information</h1>
        <p className="mt-4 text-sm leading-6 text-muted">
          Identity, threshold, and risk-band boundaries come from the API. Binary classification
          and the three risk bands are separate outputs.
        </p>
      </header>
      {state.status === "loading" ? <p role="status">Loading model information.</p> : null}
      {state.status === "unavailable" ? (
        <Card>
          <p role="alert" className="text-sm leading-6">
            {state.message}
          </p>
          <Button className="mt-4" type="button" variant="secondary" onClick={() => setAttempt((value) => value + 1)}>
            Retry
          </Button>
        </Card>
      ) : null}
      {state.status === "not-ready" ? (
        <Card>
          <p className="text-sm font-medium">API is not ready</p>
          <p className="mt-2 text-sm leading-6">{state.health.detail ?? "The model is not loaded."}</p>
          <Button className="mt-4" type="button" variant="secondary" onClick={() => setAttempt((value) => value + 1)}>
            Retry
          </Button>
        </Card>
      ) : null}
      {state.status === "ready" ? <ModelDetails model={state.model} /> : null}
    </div>
  );
}

function ModelDetails({ model }: { model: ModelResponse }) {
  return (
    <div className="space-y-4">
      <Card>
        <dl className="grid gap-4 sm:grid-cols-2">
          <div>
            <dt className="text-xs text-muted">Decision identity</dt>
            <dd className="mt-1 break-all font-mono text-sm">{model.model_version}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Model</dt>
            <dd className="mt-1 text-sm">
              {model.model} ({model.artifact_role})
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Target</dt>
            <dd className="mt-1 text-sm leading-6">{model.positive_class}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Negative class</dt>
            <dd className="mt-1 text-sm leading-6">{model.negative_class}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Binary threshold</dt>
            <dd className="mt-1 text-sm">{model.binary_threshold}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Calibration</dt>
            <dd className="mt-1 text-sm">{model.calibration_method}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Low band below</dt>
            <dd className="mt-1 text-sm">{model.risk_level_low_below}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">High band at or above</dt>
            <dd className="mt-1 text-sm">{model.risk_level_high_at_or_above}</dd>
          </div>
        </dl>
        <p className="mt-4 text-sm leading-6">{model.question}</p>
        <p className="mt-2 text-sm leading-6">{model.not_estimated}</p>
        <p className="mt-2 text-sm leading-6">{model.risk_levels_are}</p>
        <p className="mt-2 text-sm leading-6 text-muted">{model.threshold_policy}</p>
      </Card>
      <Card>
        <h2 className="text-base font-semibold">Approved features ({model.feature_count})</h2>
        <p className="mt-2 text-sm text-muted">Feature specification version {model.feature_spec_version}.</p>
        <ul className="mt-4 space-y-3">
          {model.features.map((feature) => (
            <li key={feature.name}>
              <p className="text-sm font-medium">{feature.name}</p>
              <p className="text-xs leading-5 text-muted">
                {feature.data_type}. {feature.meaning}
              </p>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
