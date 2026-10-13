import { useRef, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api, ApiError, type PredictionResponse } from "@/lib/api";
import { fieldGroups, fields, predictionFromForm, type FieldDef } from "@/lib/fields";
import { classLabel, formatProbability } from "@/lib/format";

type ResultState =
  | { status: "idle" }
  | { status: "pending" }
  | { status: "success"; prediction: PredictionResponse }
  | { status: "error"; message: string };

export function PredictPage() {
  const [result, setResult] = useState<ResultState>({ status: "idle" });
  const [formError, setFormError] = useState<string | null>(null);
  const pendingRef = useRef(false);
  const pending = result.status === "pending";

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pendingRef.current) {
      return;
    }
    pendingRef.current = true;
    const parsed = predictionFromForm(new FormData(event.currentTarget));
    if ("error" in parsed) {
      pendingRef.current = false;
      setFormError(parsed.error);
      setResult({ status: "idle" });
      return;
    }
    setFormError(null);
    setResult({ status: "pending" });
    try {
      const prediction = await api.predict(parsed.value);
      setResult({ status: "success", prediction });
    } catch (error) {
      setResult({
        status: "error",
        message: error instanceof ApiError ? error.message : "The prediction could not be completed.",
      });
    } finally {
      pendingRef.current = false;
    }
  }

  return (
    <div className="space-y-8">
      <header className="max-w-3xl">
        <p className="text-xs font-medium tracking-wide text-muted uppercase">Prediction</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">Score one reported collision</h1>
        <p className="mt-4 text-base leading-7">
          The target is fatal or serious versus slight among reported personal-injury collisions.
          The model does not estimate the probability that a collision will occur.
        </p>
      </header>
      <form className="space-y-6" noValidate onSubmit={onSubmit}>
        <fieldset className="space-y-6" disabled={pending}>
          {fieldGroups.map((group) => (
            <Card key={group}>
              <h2 className="text-base font-semibold">{group}</h2>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                {fields
                  .filter((field) => field.group === group)
                  .map((field) => (
                    <Field key={field.name} field={field} />
                  ))}
              </div>
            </Card>
          ))}
        </fieldset>
        {formError ? (
          <p className="text-sm text-navy" role="alert">
            {formError}
          </p>
        ) : null}
        <Button type="submit" disabled={pending}>
          {pending ? "Scoring" : "Score collision"}
        </Button>
      </form>
      <PredictionResult result={result} />
    </div>
  );
}

function Field({ field }: { field: FieldDef }) {
  const id = `field-${field.name}`;
  return (
    <div>
      <label className="text-sm font-medium" htmlFor={id}>
        {field.label}
      </label>
      <p className="mt-1 text-xs leading-5 text-muted" id={`${id}-hint`}>
        {field.description}
      </p>
      {field.kind === "number" ? (
        <input
          id={id}
          name={field.name}
          type="number"
          inputMode="decimal"
          min={field.min}
          max={field.max}
          step={field.step}
          aria-describedby={`${id}-hint`}
          className="mt-2 w-full rounded-md border border-line bg-white px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy"
        />
      ) : (
        <select
          id={id}
          name={field.name}
          defaultValue=""
          aria-describedby={`${id}-hint`}
          className="mt-2 w-full rounded-md border border-line bg-white px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy"
        >
          {field.choices?.map((choice) => (
            <option key={`${field.name}-${choice.label}-${choice.value}`} value={choice.value}>
              {choice.label}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}

function PredictionResult({ result }: { result: ResultState }) {
  if (result.status === "idle") {
    return (
      <Card>
        <h2 className="text-base font-semibold">Result</h2>
        <p className="mt-2 text-sm leading-6 text-muted">
          The probability, class, and risk band appear here after the API responds. Nothing is
          calculated in the browser.
        </p>
      </Card>
    );
  }
  if (result.status === "pending") {
    return <p role="status">Sending the collision to the API.</p>;
  }
  if (result.status === "error") {
    return (
      <Card>
        <h2 className="text-base font-semibold">Result</h2>
        <p className="mt-2 text-sm leading-6" role="alert">
          {result.message}
        </p>
      </Card>
    );
  }
  const prediction = result.prediction;
  return (
    <Card>
      <h2 className="text-base font-semibold">Result</h2>
      <dl className="mt-4 grid gap-4 sm:grid-cols-3">
        <div>
          <dt className="text-xs text-muted">Calibrated probability</dt>
          <dd className="mt-1 text-lg font-semibold">{formatProbability(prediction.probability)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">Binary class</dt>
          <dd className="mt-1 text-lg font-semibold">{classLabel(prediction.predicted_class_label)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">Risk band</dt>
          <dd className="mt-1 text-lg font-semibold">{prediction.risk_level}</dd>
        </div>
      </dl>
      <p className="mt-4 text-sm leading-6 text-muted">
        Risk bands are model-score categories, not safety grades or exposure-adjusted collision
        rates. The decision threshold returned with this score is {prediction.binary_threshold}.
      </p>
      <p className="mt-2 text-sm leading-6">{prediction.not_estimated}</p>
      <p className="mt-2 text-sm leading-6">{prediction.limitation}</p>
    </Card>
  );
}
