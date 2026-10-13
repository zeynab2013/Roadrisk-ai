import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppRoutes } from "@/App";

/** Test fixture. This is not a production prediction. */
const predictionFixture = {
  probability: 0.42,
  predicted_class: 1,
  predicted_class_label: "fatal_or_serious",
  risk_level: "HIGH",
  binary_threshold: 0.15,
  model_version: "fixture-decision",
  model: "fixture-model",
  artifact_role: "synthetic_test_fixture",
  threshold_policy: "fixture policy",
  question: "Was this reported collision fatal or serious?",
  not_estimated: "Whether a collision occurs.",
  limitation: "A model score is not a safety grade.",
};

const modelFixture = {
  model_version: "fixture-decision",
  model: "fixture-model",
  artifact_role: "synthetic_test_fixture",
  calibration_method: "sigmoid",
  question: "Was this reported collision fatal or serious?",
  not_estimated: "Whether a collision occurs.",
  positive_class: "Fatal or serious among reported collisions",
  negative_class: "Slight",
  binary_threshold: 0.15,
  threshold_policy: "fixture policy",
  risk_level_low_below: 0.2,
  risk_level_high_at_or_above: 0.4,
  risk_level_inclusivity: "low is below; high is at or above",
  risk_levels_are: "Model-score categories, not safety grades.",
  feature_spec_version: 1,
  features: [{ name: "hour", data_type: "numeric", meaning: "Hour of the collision." }],
  feature_count: 1,
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

describe("dashboard", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows the logo and does not treat a loaded page as a ready API", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    renderAt("/");
    expect(screen.getAllByRole("img", { name: "RoadRisk" }).length).toBeGreaterThan(0);
    expect(await screen.findByText("Unavailable")).toBeInTheDocument();
    expect(screen.queryByText("Ready")).not.toBeInTheDocument();
  });

  it("renders a successful prediction from the API response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json(predictionFixture));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderAt("/predict");
    await user.selectOptions(screen.getByLabelText("Weekday"), "1");
    await user.click(screen.getByRole("button", { name: "Score collision" }));
    expect(await screen.findByText("0.420 (42.0%)")).toBeInTheDocument();
    expect(screen.getByText("Fatal or serious")).toBeInTheDocument();
    expect(screen.getByText("HIGH")).toBeInTheDocument();
    expect(screen.getByText(/decision threshold returned with this score is 0.15/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("shows a form validation message without calling the API", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderAt("/predict");
    await user.type(screen.getByLabelText("Hour"), "99");
    await user.click(screen.getByRole("button", { name: "Score collision" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Hour must be between 0 and 23.");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows a server error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ detail: "The model is not available" }, 503)));
    const user = userEvent.setup();
    renderAt("/predict");
    await user.click(screen.getByRole("button", { name: "Score collision" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The model is not available");
  });

  it("blocks a second submit while the first request is pending", async () => {
    let resolveRequest: (value: Response) => void = () => undefined;
    const fetchMock = vi.fn().mockImplementation(
      () =>
        new Promise<Response>((resolve) => {
          resolveRequest = resolve;
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderAt("/predict");
    const pendingClick = user.click(screen.getByRole("button", { name: "Score collision" }));
    expect(await screen.findByRole("button", { name: "Scoring" })).toBeDisabled();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    resolveRequest(json(predictionFixture));
    await pendingClick;
    expect(await screen.findByText("HIGH")).toBeInTheDocument();
  });

  it("shows an empty history rather than sample rows", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ predictions: [] })));
    renderAt("/history");
    expect(await screen.findByText("No stored predictions")).toBeInTheDocument();
    expect(screen.queryByText("0.420 (42.0%)")).not.toBeInTheDocument();
  });

  it("renders stored history from the API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        json({
          predictions: [{ ...predictionFixture, id: 7, created_at: "2026-10-10T18:00:00.000Z" }],
        }),
      ),
    );
    renderAt("/history");
    expect(await screen.findByText("7")).toBeInTheDocument();
    expect(screen.getByText("Fatal or serious")).toBeInTheDocument();
    expect(screen.getByText("HIGH")).toBeInTheDocument();
  });

  it("shows a history failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ detail: "Prediction history is unavailable" }, 503)));
    renderAt("/history");
    expect(await screen.findByRole("alert")).toHaveTextContent("Prediction history is unavailable");
  });

  it("renders model metadata from the API", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string) => {
      if (String(url).endsWith("/health")) {
        return Promise.resolve(
          json({ status: "ok", ready: true, model_version: "fixture-decision", model: "fixture-model", artifact_role: "synthetic_test_fixture", detail: null }),
        );
      }
      return Promise.resolve(json(modelFixture));
    }));
    renderAt("/model");
    expect(await screen.findByText("fixture-decision")).toBeInTheDocument();
    expect(screen.getByText("Fatal or serious among reported collisions")).toBeInTheDocument();
    expect(screen.getByText("0.2")).toBeInTheDocument();
    expect(screen.getByText("hour")).toBeInTheDocument();
  });

  it("does not mark the model ready when health says it is not", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        json({
          status: "ok",
          ready: false,
          model_version: null,
          model: null,
          artifact_role: null,
          detail: "The model is not loaded.",
        }),
      ),
    );
    renderAt("/model");
    expect(await screen.findByText("API is not ready")).toBeInTheDocument();
    expect(screen.queryByText("fixture-decision")).not.toBeInTheDocument();
  });
});
