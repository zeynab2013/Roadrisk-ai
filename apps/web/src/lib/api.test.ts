import { afterEach, describe, expect, it, vi } from "vitest";

import { apiBaseUrl, createApi, DEFAULT_API_BASE_URL } from "@/lib/api";

describe("API client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("uses the configured base URL and the local default", () => {
    expect(DEFAULT_API_BASE_URL).toBe("http://127.0.0.1:8000");
    expect(apiBaseUrl({ VITE_API_BASE_URL: "http://example.test/" })).toBe("http://example.test");
    expect(apiBaseUrl({})).toBe(DEFAULT_API_BASE_URL);
    expect(apiBaseUrl({}, "/api")).toBe("/api");
    expect(apiBaseUrl({ VITE_API_BASE_URL: "http://example.test" }, "")).toBe("");
  });

  it("reports a validation error from the API body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: [{ loc: ["body", "hour"], msg: "value is invalid" }] }), {
          status: 422,
        }),
      ),
    );
    const client = createApi("http://api.test");
    await expect(client.predict(blankRequest())).rejects.toThrow("hour: value is invalid");
    expect(fetch).toHaveBeenCalledWith(
      "http://api.test/predictions",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("does not invent a prediction when the API cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("failed")));
    await expect(createApi().history()).rejects.toThrow("The RoadRisk API is not reachable.");
  });
});

function blankRequest() {
  return {
    longitude: null,
    latitude: null,
    hour: null,
    weekday: null,
    month: null,
    season: null,
    first_road_class: null,
    road_type: null,
    speed_limit: null,
    junction_detail: null,
    junction_control: null,
    second_road_class: null,
    pedestrian_crossing: null,
    light_conditions: null,
    weather_conditions: null,
    road_surface_conditions: null,
    special_conditions_at_site: null,
    urban_or_rural_area: null,
    trunk_road_flag: null,
  };
}
