import type { PredictionRequest } from "@/lib/api";

/**
 * Form choices grounded in the repository.
 * Codes come from `src/roadrisk/data/codebook.py`.
 * `-1` is sent as null (`missing`). A codebook unknown code is sent as `unknown`.
 * Labels are included only where the feature specification names them.
 */

export type FieldGroup = "Location" | "Time" | "Road" | "Junction" | "Conditions";

export type Choice = {
  value: string;
  label: string;
};

export type FieldDef = {
  name: keyof PredictionRequest;
  label: string;
  description: string;
  group: FieldGroup;
  kind: "number" | "select";
  min?: number;
  max?: number;
  step?: string;
  choices?: Choice[];
};

const missing: Choice = { value: "", label: "Missing" };
const unknown: Choice = { value: "unknown", label: "unknown" };

function codes(values: string[], labels: Record<string, string> = {}, withUnknown = false): Choice[] {
  const options = values.map((value) => ({
    value,
    label: labels[value] ? `${value} — ${labels[value]}` : `Code ${value}`,
  }));
  if (withUnknown) {
    options.push(unknown);
  }
  options.push(missing);
  return options;
}

export const fieldGroups: FieldGroup[] = ["Location", "Time", "Road", "Junction", "Conditions"];

export const fields: FieldDef[] = [
  {
    name: "longitude",
    label: "Longitude",
    description: "Decimal degrees. Leave blank when the coordinate is missing.",
    group: "Location",
    kind: "number",
    step: "any",
  },
  {
    name: "latitude",
    label: "Latitude",
    description: "Decimal degrees. Leave blank when the coordinate is missing.",
    group: "Location",
    kind: "number",
    step: "any",
  },
  {
    name: "urban_or_rural_area",
    label: "Urban or rural",
    description: "Codebook codes 1 Urban, 2 Rural, and 3 Unallocated.",
    group: "Location",
    kind: "select",
    choices: codes(["1", "2", "3"], { "1": "Urban", "2": "Rural", "3": "Unallocated" }),
  },
  {
    name: "hour",
    label: "Hour",
    description: "Hour of the collision, 0 to 23. Leave blank when the time is missing.",
    group: "Time",
    kind: "number",
    min: 0,
    max: 23,
    step: "1",
  },
  {
    name: "weekday",
    label: "Weekday",
    description: "Codebook: 1 Sunday through 7 Saturday.",
    group: "Time",
    kind: "select",
    choices: codes(["1", "2", "3", "4", "5", "6", "7"], {
      "1": "Sunday",
      "2": "Monday",
      "3": "Tuesday",
      "4": "Wednesday",
      "5": "Thursday",
      "6": "Friday",
      "7": "Saturday",
    }),
  },
  {
    name: "month",
    label: "Month",
    description: "Month of the collision, 1 to 12. Leave blank when the date is missing.",
    group: "Time",
    kind: "number",
    min: 1,
    max: 12,
    step: "1",
  },
  {
    name: "season",
    label: "Season",
    description: "Meteorological season derived from the month. Winter is December to February.",
    group: "Time",
    kind: "select",
    choices: [
      { value: "winter", label: "winter — December to February" },
      { value: "spring", label: "spring — March to May" },
      { value: "summer", label: "summer — June to August" },
      { value: "autumn", label: "autumn — September to November" },
      missing,
    ],
  },
  {
    name: "first_road_class",
    label: "First road class",
    description: "Class of the first road. The repository lists codes 1 to 6 and does not name each code.",
    group: "Road",
    kind: "select",
    choices: codes(["1", "2", "3", "4", "5", "6"]),
  },
  {
    name: "road_type",
    label: "Road type",
    description: "Road layout. Code 9 is the unknown token. Code 12 stays 12.",
    group: "Road",
    kind: "select",
    choices: codes(["1", "2", "3", "6", "7", "12"], {}, true),
  },
  {
    name: "speed_limit",
    label: "Speed limit",
    description: "Posted limit. Valid public-highway values are 20, 30, 40, 50, 60, and 70. Code 99 is unknown.",
    group: "Road",
    kind: "select",
    choices: codes(["20", "30", "40", "50", "60", "70"], {}, true),
  },
  {
    name: "trunk_road_flag",
    label: "Trunk road",
    description: "Code 1 trunk, code 2 non-trunk.",
    group: "Road",
    kind: "select",
    choices: codes(["1", "2"], { "1": "Trunk", "2": "Non-trunk" }),
  },
  {
    name: "junction_detail",
    label: "Junction detail",
    description: "2024 code list. Code 99 is the unknown token.",
    group: "Junction",
    kind: "select",
    choices: codes(["0", "13", "16", "17", "18", "19"], {}, true),
  },
  {
    name: "junction_control",
    label: "Junction control",
    description: "How the junction is controlled. Code 9 is the unknown token.",
    group: "Junction",
    kind: "select",
    choices: codes(["0", "1", "2", "3", "4"], {}, true),
  },
  {
    name: "second_road_class",
    label: "Second road class",
    description: "Second road at a junction. Code 9 is the unknown token.",
    group: "Junction",
    kind: "select",
    choices: codes(["0", "1", "2", "3", "4", "5", "6"], {}, true),
  },
  {
    name: "pedestrian_crossing",
    label: "Pedestrian crossing",
    description: "2024 code list. Code 99 is the unknown token.",
    group: "Junction",
    kind: "select",
    choices: codes(["0", "11", "12", "13", "14", "15", "16", "17"], {}, true),
  },
  {
    name: "light_conditions",
    label: "Light conditions",
    description: "Codebook codes, including 7. The repository does not name each code here.",
    group: "Conditions",
    kind: "select",
    choices: codes(["1", "4", "5", "6", "7"]),
  },
  {
    name: "weather_conditions",
    label: "Weather",
    description: "Reported weather category. Code 9 is the unknown token.",
    group: "Conditions",
    kind: "select",
    choices: codes(["1", "2", "3", "4", "5", "6", "7", "8"], {}, true),
  },
  {
    name: "road_surface_conditions",
    label: "Road surface",
    description: "Surface state. Code 9 is the unknown token.",
    group: "Conditions",
    kind: "select",
    choices: codes(["1", "2", "3", "4", "5", "6", "7"], {}, true),
  },
  {
    name: "special_conditions_at_site",
    label: "Special conditions",
    description: "Site conditions such as roadworks. Code 9 is the unknown token.",
    group: "Conditions",
    kind: "select",
    choices: codes(["0", "1", "2", "3", "4", "5", "6", "7"], {}, true),
  },
];

export function emptyPrediction(): PredictionRequest {
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

export function predictionFromForm(form: FormData): { value: PredictionRequest } | { error: string } {
  const value = emptyPrediction();
  for (const field of fields) {
    const raw = String(form.get(field.name) ?? "").trim();
    if (field.kind === "select") {
      assignCategory(value, field.name, raw ? raw : null);
      continue;
    }
    if (!raw) {
      assignNumber(value, field.name, null);
      continue;
    }
    const parsed = Number(raw);
    if (!Number.isFinite(parsed)) {
      return { error: `${field.label} must be a number or blank.` };
    }
    if (field.min !== undefined && (parsed < field.min || parsed > (field.max ?? parsed))) {
      return { error: `${field.label} must be between ${field.min} and ${field.max}.` };
    }
    assignNumber(value, field.name, parsed);
  }
  return { value };
}

function assignNumber(value: PredictionRequest, name: keyof PredictionRequest, parsed: number | null) {
  if (name === "longitude" || name === "latitude" || name === "hour" || name === "month") {
    value[name] = parsed;
  }
}

function assignCategory(value: PredictionRequest, name: keyof PredictionRequest, parsed: string | null) {
  if (name !== "longitude" && name !== "latitude" && name !== "hour" && name !== "month") {
    value[name] = parsed;
  }
}
