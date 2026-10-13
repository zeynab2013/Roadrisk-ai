# Prediction API

Status: Phase 8, with Phase 9 history and a Phase 10 read-only area summary. The service scores the frozen Phase 6 pipeline and applies the Phase 7 band file. It does not train, recalibrate, or rescore 2025.

The question is whether a reported personal-injury collision was fatal or serious rather than slight. The probability is that severity probability. It is not the probability that a collision occurs. `LOW`, `MEDIUM`, and `HIGH` are research bands for the model score. They are not a safety grade and they are not an exposure-adjusted collision rate. The policy is in [risk policy](risk-policy.md). The frozen evaluation is in [phase 6](phase6.md).

The dashboard in `apps/web` calls this service. See [frontend](frontend.md).

## Run locally

From the repository root, with `.venv312` and the API extra installed:

```powershell
.\.venv312\Scripts\python.exe -m pip install -e ".[dev,ml,api]"
.\.venv312\Scripts\python.exe -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

Uvicorn loads `apps` from the current directory. The bind address above is the local machine. There is no production URL in the repository.

Open `http://127.0.0.1:8000/docs` for the generated schema. The process reads artifacts at startup. If they are missing or do not match, the process stays up, `GET /health` reports `ready: false`, and `GET /model` and `POST /predictions` return 503. The service does not fit a replacement model.

## Configuration

| Variable | Default | Role |
| --- | --- | --- |
| `ROADRISK_DATA_DIR` | `data` | Root for `models/` when the two paths below are not set |
| `ROADRISK_PHASE6_DIR` | `$ROADRISK_DATA_DIR/models/phase6-v1` | Frozen decision and `selected-pipeline.joblib` |
| `ROADRISK_BANDS_PATH` | `$ROADRISK_DATA_DIR/models/phase7-v1/risk-bands.json` | Stored `LOW` / `MEDIUM` / `HIGH` boundaries |
| `ROADRISK_LOG_LEVEL` | `INFO` | Library log level |
| `ROADRISK_DATABASE_URL` | `sqlite:///` plus `data/roadrisk.sqlite3` | Prediction history. SQLite needs no credentials |
| `ROADRISK_CORS_ORIGINS` | `http://127.0.0.1:5173,http://localhost:5173` | Browser origins allowed to call the API |

Relative paths are resolved from the process working directory. The band file must name the same decision hash, pipeline hash, and binary threshold as the frozen decision. This install was checked with FastAPI 0.143.0, Uvicorn 0.54.0, and Pydantic 2.14.0. The library module `roadrisk.inference.service` does not import FastAPI.

## Artifacts

`open_session` uses `load_frozen_model` and `load_risk_bands`. It checks the decision hash, the pipeline SHA-256, feature specification version 1, and that the band file's `binary_threshold` equals the frozen threshold `0.15`. A missing file, a bad hash, unreadable JSON, or a band file that says 2025 was used raises, and the scoring routes stay unavailable.

The Phase 7 boundaries stay the stored quantiles `0.196970155937929` and `0.3126165522731136`. The API does not recompute them. A probability at or above `0.15` is the fatal-or-serious class even when the band is `LOW`, because the class threshold and the band cuts are different fields.

## Endpoints

There is no batch route. A JSON array is rejected with 422. `GET /predictions` lists accepted predictions. It does not accept a query, a filter, or a file path.

### `GET /health`

The process is up. `ready` is true only when an artifact loaded.

```json
{
  "status": "ok",
  "ready": true,
  "model_version": "9461dce554913b7617c1632d5bd8a23ab3e4185542c3f5e65baab5fac14ef09b",
  "model": "hist_gradient_boosting",
  "artifact_role": "frozen_phase6"
}
```

`model_version` is the frozen decision SHA-256. When the artifact did not load, `ready` is false and `detail` explains why. That response is still HTTP 200.

### `GET /model`

Returns the target, the threshold, the stored band cuts, and the 19 approved features. It does not score a row. HTTP 503 when no artifact is loaded.

### `POST /predictions`

One object of approved features. Every feature key is required. A numeric feature may be `null` when the source value is missing. A categorical feature may be `null` or `""`, which the pipeline treats as missing. Categorical values are strings, including codebook codes such as `"1"`.

Numeric features: `longitude`, `latitude`, `hour`, `month`. The other 15 features are categorical strings. Approved season values are `winter`, `spring`, `summer`, and `autumn`. A codebook unknown code is sent as the string `unknown`, not the original code such as `99`.

```json
{
  "longitude": -0.12,
  "latitude": 51.5,
  "hour": 8,
  "weekday": "2",
  "month": 1,
  "season": "winter",
  "first_road_class": "3",
  "road_type": "6",
  "speed_limit": "30",
  "junction_detail": "0",
  "junction_control": "4",
  "second_road_class": "6",
  "pedestrian_crossing": "0",
  "light_conditions": "1",
  "weather_conditions": "1",
  "road_surface_conditions": "1",
  "special_conditions_at_site": "0",
  "urban_or_rural_area": "1",
  "trunk_road_flag": "2"
}
```

A successful body includes `probability`, `predicted_class` (`1` fatal or serious, `0` slight), `predicted_class_label`, `risk_level`, `binary_threshold`, `model_version`, `threshold_policy`, `question`, `not_estimated`, and `limitation`. The probability, the class, and the band are separate. The response does not add a history id. After that response is produced, the API stores those fields and a UTC timestamp. The feature values are not stored. If the write fails, the route returns 503 and does not present the score as a completed request.

| Condition | HTTP status |
| --- | --- |
| Missing feature, extra field, label, or non-numeric value in a numeric field | 422 |
| JSON array, or a body that is not JSON | 422 |
| Artifact missing, unreadable, or not tied to this decision | 503 |
| Model returns a probability outside `[0, 1]` | 500 |
| History storage cannot save the accepted prediction | 503 |

### `GET /predictions`

Returns `{"predictions": [...]}`. Each item has `id`, `created_at`, and the same prediction fields as a successful `POST /predictions` response. SQLite stores `created_at` as UTC text `YYYY-MM-DDTHH:MM:SS.ffffff+00:00` because it has no timezone type. That form is defined in `src/roadrisk/persistence/models.py`. The HTTP field is a datetime. A response from the running API on 13 October 2026 used a `Z` suffix. The history test accepts either `Z` or `+00:00`.

Order is oldest `created_at` first. Rows with the same timestamp are ordered by ascending `id`. The route takes no parameters. A storage failure returns 503 with `{"detail": "Prediction history is unavailable"}`. The body does not include the database URL.

Labels and excluded columns, including `collision_severity` and `severity_serious_or_fatal`, are not features. The request model rejects them.

### `GET /area-summaries`

Reads the saved Phase 7 `group-summary.json` beside the band file. It does not score rows and does not rebuild the summary from prediction history. History does not store the 19 inputs.

The response is returned only when the sibling `risk-bands.json` names the same `decision_sha256` as the loaded model, and `grouping_field` is `urban_or_rural_area`. A missing or unreadable file returns 503 with `{"detail": "Area summary is not available"}`. A different decision returns 409 with `{"detail": "Area summary is not tied to the loaded model"}`.

`groups` lists every saved class, including classes below `minimum_support`. `supported_groups` is that support filter, not a danger ranking. `not_estimated` and `limitation` say that the counts are recorded collisions and are not an exposure-adjusted rate or a statement that an area is unsafe.

The API allows the local Vite origins so the dashboard on port 5173 can call port 8000. Credentials are not sent, and `*` is not an allowed origin.

## Correlation ID

Every response includes `X-Correlation-ID`. A request may send that header. The value is kept when it matches `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`: 1 to 64 characters, the first character a letter or digit, and the rest letters, digits, `.`, `_`, or `-`. A value that starts with `.`, `_`, or `-` is replaced. A missing, empty, oversized, or multiline value is also replaced, so a caller cannot insert extra log lines.

A response with status 400 or higher writes one error log line with the method, path, status, and correlation ID. The line does not include the request body, the 19 feature values, the database URL, or a filesystem path. A missing model artifact is reported to the client as `Model artifacts are not loaded`. The client body does not include the artifact path.

## Continuous integration

`.github/workflows/ci.yml` is configured to run, on pull requests and on pushes to `main` or `master`:

```text
python -m pip install -e ".[dev,ml,api]"
python -m ruff check src tests apps
python -m pytest
```

Python 3.12 is the runner version because the `ml` extra is pinned from that environment. The workflow does not download the collision extract and does not run `train`, `select`, `evaluate`, or `bands`. It was checked by running those two commands locally. GitHub has not executed the workflow from this checkout. Frontend `npm test`, `npm run lint`, and `npm run build` remain local commands.

## Tests

API tests build a synthetic classifier named `fixture_not_phase6` with `artifact_role` `synthetic_test_fixture`. That fixture is not the Phase 6 pipeline. Health and model responses return its version. The real artifacts are read only when they are already on disk, and the test checks their bytes afterwards.

```powershell
.\.venv312\Scripts\python.exe -m pytest tests/integration/test_api.py tests/integration/test_history.py tests/integration/test_areas.py
.\.venv312\Scripts\python.exe -m ruff check src tests apps
```

The full suite is `python -m pytest` from the same environment. It does not run `select` or `evaluate`.
