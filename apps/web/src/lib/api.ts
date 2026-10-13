/**
 * Typed client for the RoadRisk API.
 * Responses come from the server. This module does not score collisions.
 */

export const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

export type PredictionRequest = {
  longitude: number | null;
  latitude: number | null;
  hour: number | null;
  weekday: string | null;
  month: number | null;
  season: string | null;
  first_road_class: string | null;
  road_type: string | null;
  speed_limit: string | null;
  junction_detail: string | null;
  junction_control: string | null;
  second_road_class: string | null;
  pedestrian_crossing: string | null;
  light_conditions: string | null;
  weather_conditions: string | null;
  road_surface_conditions: string | null;
  special_conditions_at_site: string | null;
  urban_or_rural_area: string | null;
  trunk_road_flag: string | null;
};

export type ClassLabel = "slight" | "fatal_or_serious";
export type RiskLevel = "LOW" | "MEDIUM" | "HIGH";

export type PredictionResponse = {
  probability: number;
  predicted_class: number;
  predicted_class_label: ClassLabel;
  risk_level: RiskLevel;
  binary_threshold: number;
  model_version: string;
  model: string;
  artifact_role: string;
  threshold_policy: string;
  question: string;
  not_estimated: string;
  limitation: string;
};

export type PredictionHistoryItem = PredictionResponse & {
  id: number;
  created_at: string;
};

export type PredictionHistoryResponse = {
  predictions: PredictionHistoryItem[];
};

export type FeatureInfo = {
  name: string;
  data_type: string;
  meaning: string;
};

export type ModelResponse = {
  model_version: string;
  model: string;
  artifact_role: string;
  calibration_method: string;
  question: string;
  not_estimated: string;
  positive_class: string;
  negative_class: string;
  binary_threshold: number;
  threshold_policy: string;
  risk_level_low_below: number;
  risk_level_high_at_or_above: number;
  risk_level_inclusivity: string;
  risk_levels_are: string;
  feature_spec_version: number;
  features: FeatureInfo[];
  feature_count: number;
};

export type HealthResponse = {
  status: "ok";
  ready: boolean;
  model_version: string | null;
  model: string | null;
  artifact_role: string | null;
  detail: string | null;
};

export type AreaGroup = {
  area_id: string;
  label: string;
  collisions: number;
  category_counts: Record<string, number>;
  category_shares: Record<string, number | null>;
  mean_predicted_probability: number | null;
};

export type AreaSummaryResponse = {
  grouping_field: string;
  grouping_reason: string;
  population: string;
  minimum_support: number;
  rows: number;
  missing_location_rows: number;
  unsupported_location_rows: number;
  groups: AreaGroup[];
  supported_groups: AreaGroup[];
  not_estimated: string;
  limitation: string;
};

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function apiBaseUrl(
  env: { VITE_API_BASE_URL?: string } = import.meta.env,
  runtimeUrl?: string,
): string {
  const runtime = runtimeUrl !== undefined ? runtimeUrl : readRuntimeConfig();
  if (runtime !== undefined) {
    return runtime.trim().replace(/\/$/, "");
  }
  const configured = env.VITE_API_BASE_URL?.trim();
  return configured ? configured.replace(/\/$/, "") : DEFAULT_API_BASE_URL;
}

function readRuntimeConfig(): string | undefined {
  if (typeof window === "undefined") {
    return undefined;
  }
  const record = window as unknown as Record<string, unknown>;
  if (!Object.prototype.hasOwnProperty.call(record, "__ROADRISK_API_BASE_URL__")) {
    return undefined;
  }
  const value = record.__ROADRISK_API_BASE_URL__;
  return typeof value === "string" ? value : undefined;
}

export function createApi(baseUrl = apiBaseUrl()) {
  return {
    health: () => request<HealthResponse>(baseUrl, "/health"),
    model: () => request<ModelResponse>(baseUrl, "/model"),
    predict: (body: PredictionRequest) =>
      request<PredictionResponse>(baseUrl, "/predictions", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    history: () => request<PredictionHistoryResponse>(baseUrl, "/predictions"),
    areaSummary: () => request<AreaSummaryResponse>(baseUrl, "/area-summaries"),
  };
}

export const api = createApi();

async function request<T>(baseUrl: string, path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError(0, "The RoadRisk API is not reachable.");
  }
  const text = await response.text();
  const body = parseJson(text);
  if (!response.ok) {
    throw new ApiError(response.status, detailMessage(body, response.status));
  }
  if (body === undefined) {
    throw new ApiError(response.status, "The API returned a response that was not JSON.");
  }
  return body as T;
}

function parseJson(text: string): unknown {
  if (!text) {
    return undefined;
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return undefined;
  }
}

function detailMessage(body: unknown, status: number): string {
  if (!body || typeof body !== "object" || !("detail" in body)) {
    return `The API returned status ${status}.`;
  }
  const detail = body.detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (Array.isArray(detail)) {
    const messages = detail.map(formatIssue).filter((item) => item.length > 0);
    if (messages.length > 0) {
      return messages.join(" ");
    }
  }
  return `The API returned status ${status}.`;
}

function formatIssue(issue: unknown): string {
  if (!issue || typeof issue !== "object" || !("msg" in issue)) {
    return "";
  }
  const msg = String(issue.msg);
  if (!("loc" in issue) || !Array.isArray(issue.loc)) {
    return msg;
  }
  const loc = issue.loc.filter((part) => part !== "body").join(".");
  return loc ? `${loc}: ${msg}` : msg;
}
