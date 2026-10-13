# RoadRisk

RoadRisk estimates the severity of a reported UK personal-injury collision. Given the circumstances on that record, it estimates whether the collision was fatal or serious rather than slight.

It does not estimate whether a collision will occur. A collision probability would need traffic exposure at the same place and time, and the files used here do not contain that exposure.

**Package version `0.1.0`.** The model card is [docs/model-card.md](docs/model-card.md). The dataset card is [docs/dataset-card.md](docs/dataset-card.md). No GitHub release has been published.

## What the system does

The frozen model is histogram gradient boosting with sigmoid calibration. The fatal-or-serious class is probability at or above `0.15`. `LOW`, `MEDIUM`, and `HIGH` are separate research bands for that probability. They are not a safety grade and they are not an official rating.

| Piece | What it does |
| --- | --- |
| `src/roadrisk` | Checks the collision extract, builds the 19-feature table, trains baselines, and loads the frozen pipeline. The inference service does not import the database layer |
| `apps/api` | FastAPI service. `GET /health`, `GET /model`, `POST /predictions`, `GET /predictions`, `GET /area-summaries` |
| `apps/web` | React dashboard. It calls the API. It does not score rows and it does not open the database |
| SQLite history | Stores the accepted prediction. It does not store the 19 feature values |

```text
reported collision → 19 approved features → frozen pipeline
        → probability, class, research band → API → dashboard
                                      ↘ prediction history
```

The decision record and the held-out metrics are in [docs/phase6.md](docs/phase6.md). Band rules are in [docs/risk-policy.md](docs/risk-policy.md). The HTTP contract is in [docs/api.md](docs/api.md).

## Model

| Item | Value |
| --- | --- |
| Model | `hist_gradient_boosting` |
| Calibration | Sigmoid, fit on 2021–2023 out-of-fold scores |
| Training years | 2021–2023 |
| Validation year | 2024, used to choose calibration and the threshold |
| Held-out year | 2025, scored once at `2026-10-10T16:30:04+00:00` |
| Threshold | `0.15` |
| `LOW` below | `0.196970155937929` |
| `HIGH` at or above | `0.3126165522731136` |
| Decision SHA-256 | `9461dce554913b7617c1632d5bd8a23ab3e4185542c3f5e65baab5fac14ef09b` |

A probability at or above `0.15` is the fatal-or-serious class even when the band is `LOW`, because `0.15` is below the lower band cut.

The 2025 metrics below are copied from `data/models/phase6-v1/test-evaluation.json`. They were not recomputed for this page. Positive class `1` is fatal or serious. The confusion-matrix order is true class `0` then `1` by row, and predicted class `0` then `1` by column.

| Metric | 2025 value |
| --- | --- |
| Rows | 101,525 |
| Positive rows | 26,644 |
| Precision | 0.2874644131552166 |
| Recall | 0.8375243957363759 |
| F1 | 0.4280192958732533 |
| Accuracy | 0.4125486333415415 |
| Average precision | 0.35679507352024975 |
| ROC-AUC | 0.6078228667181302 |
| Brier score | 0.19020457244778005 |
| Log loss | 0.5691451034690374 |
| Confusion matrix | `[[19569, 55312], [4329, 22315]]` |

These figures do not show that the model is reliable for a road-safety decision. Discrimination is modest, most rows are predicted positive at this threshold, and reporting practice can change. The full limitation statement is in the [model card](docs/model-card.md).

`data/models/phase6-v1/frozen-config.json` still says `test_year_scored: false`. That file is the snapshot from `2026-10-10T16:28:53+00:00`, before the score. The completed score is `test-evaluation.json`.

## Dataset

The collision table is the Department for Transport Road Safety Open Data file `dft-road-casualty-statistics-collision-last-5-years.csv`, years 2021–2025, retrieved 9 October 2026. The manifest records 513,801 data rows, 97,669,586 bytes, and SHA-256 `06a03c0e5504175e23ed98e3e0b4767ac61d396c073405a1bddab9339c18f948`.

The data licence recorded in `configs/data_manifest.json` is Open Government Licence v3.0. The code in this repository is MIT. Those are different licences. The catalogue page was not re-fetched for the dataset card.

The raw CSV and the codebook are gitignored. Their URLs are the ones already written in [configs/data_manifest.json](configs/data_manifest.json). Details, year counts, and what the file does not contain are in the [dataset card](docs/dataset-card.md).

## Install

Python 3.10 or newer can install the package. The `ml` extra is pinned from the Python 3.12.10 environment that trained the frozen pipeline. `.python-version` records `3.12`. Use that version to score with the saved pipeline.

From the repository root on Windows:

```powershell
py -3.12 -m venv .venv312
.\.venv312\Scripts\Activate.ps1
python -m pip install -e ".[dev,ml,api]"
```

`dev` installs pytest and Ruff. `ml` installs NumPy, pandas, scikit-learn, and joblib. `api` installs FastAPI, Uvicorn, HTTPX, and SQLAlchemy. Versions are in [pyproject.toml](pyproject.toml). This page does not change them.

The dashboard is `apps/web`. The checks recorded below used Node.js 24.20.0. From `apps/web`:

```powershell
npm install
```

`npm install` uses `package-lock.json`.

## Run the API and dashboard

Start the API from the repository root after the frozen artifacts are in place:

```powershell
.\.venv312\Scripts\python.exe -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

Then open:

- Health: `http://127.0.0.1:8000/health`
- Interactive schema: `http://127.0.0.1:8000/docs`
- Model identity: `http://127.0.0.1:8000/model`
- History: `http://127.0.0.1:8000/predictions`

`ready` is true only when the frozen pipeline and the band file loaded. A missing artifact stays HTTP 200 with `ready: false`. `GET /model` and `POST /predictions` then return HTTP 503 with `{"detail":"Model artifacts are not loaded"}`.

From `apps/web`:

```powershell
npm run dev
```

Vite normally serves `http://127.0.0.1:5173`. The API allows that origin and `http://localhost:5173`. Pages are `/`, `/predict`, `/history`, `/model`, and `/areas`. Frontend notes are in [docs/frontend.md](docs/frontend.md).

`VITE_API_BASE_URL` is read when Vite builds or serves the dashboard. When it is unset, the client uses `http://127.0.0.1:8000`.

## Docker

`compose.yaml` defines two services. The API image is built from `apps/api/Dockerfile`. The dashboard image is built from `apps/web/Dockerfile`. The API listens on `0.0.0.0:8000` inside the container. Compose publishes host port `8000` for the API and host port `8080` for the dashboard.

From the repository root, with Docker Compose and the artifact directories below:

```powershell
docker compose up --build
```

Then:

- Dashboard: `http://127.0.0.1:8080`
- API health: `http://127.0.0.1:8000/health`
- API schema: `http://127.0.0.1:8000/docs`
- History: `http://127.0.0.1:8000/predictions`
- Same health check through the dashboard: `http://127.0.0.1:8080/api/health`

The browser does not call the Docker name `api`. At startup the web container writes `/config.js` with `ROADRISK_PUBLIC_API_BASE_URL`, default `/api`. nginx forwards `/api/` to `http://api:8000/` on the Compose network. Changing `VITE_API_BASE_URL` after the image is built does not change that bundle. Set `ROADRISK_PUBLIC_API_BASE_URL` and recreate the web container instead.

A refresh of `/predict`, `/history`, `/model`, or `/areas` stays on the dashboard. Those paths are not proxied to the API. The API model route is `/api/model` from the browser, which nginx forwards to `GET /model`.

`.env` is not required. Optional names are in [.env.example](.env.example). Compose does not start PostgreSQL. Pointing `ROADRISK_DATABASE_URL` at a PostgreSQL SQLAlchemy URL is a later configuration change, not a service in this file.

The image definitions exclude `.env`, `data/raw`, virtual environments, and `data/models`. The frozen files are mounted read-only. The container does not train a replacement when they are missing.

On 13 October 2026, disposable projects reused the existing images `roadrisk-api:latest` and `roadrisk-web:latest`. Those checks did not rebuild the images. A fresh `docker compose up --build` has not been recorded as a passed check. GitHub Actions has not run Docker.

## Database

Local API, when `ROADRISK_DATABASE_URL` is unset: SQLite file `data/roadrisk.sqlite3` under the process working directory. The URL is built in `src/roadrisk/config.py`.

Compose sets:

```text
ROADRISK_DATABASE_URL=sqlite:////var/lib/roadrisk/roadrisk.sqlite3
```

That file is the named volume `roadrisk-history`, mounted at `/var/lib/roadrisk`. For the default Compose project name `roadrisk`, Docker stores it as `roadrisk_roadrisk-history`.

The schema is created on the first history read or write. Startup does not delete an existing database. `GET /health` does not create the file. Feature payloads are not stored.

`docker compose down` stops the stack and keeps the volume. `docker compose down -v` deletes the volume and the stored predictions. Do not use `-v` against a project whose history you need. The volume `roadrisk_roadrisk-history` already holds a local prediction row. A disposable test must use another Compose project name.

## Frozen artifacts

Scoring reads three files. Area summaries also read a fourth. All of them live under gitignored `data/models/`. The tracked list is [docs/artifact-manifest.json](docs/artifact-manifest.json). Those hashes identify the existing frozen files. They are not a recipe for recreating the files by training.

A clean checkout cannot download them. This repository has no Git remote and no verified release-asset URL. Do not invent one. Copy the files onto the destination paths below from the machine that already holds these exact bytes, then verify them. A future release must publish these exact files as versioned assets, or provide another documented delivery method that is checked with the same SHA-256 values. Running `select`, `evaluate`, or `bands` is not a substitute. A new fit is not this decision, and `evaluate` must not be run again to replace the recorded 2025 score.

From the repository root:

```powershell
python scripts/verify_frozen_artifacts.py
```

The script reads the manifest, hashes each file, and exits nonzero when a required file is missing or any listed file has a different hash. It does not load the pipeline and it does not write or download files. Python 3.10 or newer is enough. No extra packages are required.

| Path | SHA-256 | Required for |
| --- | --- | --- |
| `data/models/phase6-v1/frozen-config.json` | `18a0287a9f3ee98dcd285a539c3a6581a1c33839427f9a4a36255bfb5bfbc082` | Loading the decision |
| `data/models/phase6-v1/selected-pipeline.joblib` | `43143b15178c5dc2dbe5c79ed6e12e1217d5ba6cefab737f5f7ac24f508bb478` | Scoring |
| `data/models/phase7-v1/risk-bands.json` | `692aa0624a50dcc7613afafc1e53269f587b93f45d64ad9653b230833eb10846` | Band cuts. `binary_threshold` must be `0.15` |
| `data/models/phase7-v1/group-summary.json` | `41b078e73eecad94157b5ca790d018cd54421e9998c19af009c8ace5d1f97e4e` | `GET /area-summaries` only |

`data/models/phase6-v1/test-evaluation.json` (`c96ccef76c88766ff94febc175c3dd7b34f9bb91e86bc350cb4ea555c6b26432`) is the 2025 metric record. The API does not need it to score.

Defaults, if the environment variables are unset, are `data/models/phase6-v1` and `data/models/phase7-v1/risk-bands.json` under the working directory. Compose sets `ROADRISK_PHASE6_DIR=/models/phase6-v1` and `ROADRISK_BANDS_PATH=/models/phase7-v1/risk-bands.json`, and mounts the host directory `ROADRISK_MODELS_DIR` (default `./data/models`) read-only at `/models`.

The collision CSV is a separate download. Its URL is already in the manifest:

```powershell
python -m roadrisk.data download --manifest configs/data_manifest.json
python -m roadrisk.data verify --manifest configs/data_manifest.json --inspect-header
```

That download does not produce the frozen pipeline.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| `GET /health` is HTTP 200 with `ready: false` | `frozen-config.json`, `selected-pipeline.joblib`, and `risk-bands.json` are missing or their hashes do not match. The response detail is `Model artifacts are not loaded`. It does not include a filesystem path. Compose will not start the dashboard until `ready` is true |
| `GET /model` or `POST /predictions` is HTTP 503 | Same missing-artifact condition, or history storage failed after a successful score. A storage failure says `The prediction could not be stored` |
| `GET /area-summaries` is HTTP 503 or 409 | `group-summary.json` is missing, or its decision hash does not match the loaded model |
| Port 8000 or 8080 is already in use | Another process, including an existing `roadrisk` Compose project, already published that port. Stop that process or change the host port in `compose.yaml`. Do not point a second project at `roadrisk_roadrisk-history` |
| Dashboard calls `http://127.0.0.1:8000` from inside Docker and fails | The page was built without the runtime `/api` setting. Recreate the web container so it rewrites `/config.js`. Do not assume `localhost` inside the browser is the API container |
| History disappeared after `docker compose down -v` | `-v` deletes the named volume. `docker compose down` without `-v` keeps it |
| A new local `data/roadrisk.sqlite3` appears | The API was started without `ROADRISK_DATABASE_URL`, so history is the file under `data/` in the working directory. That is separate from the Compose volume |

## Checks that have actually been run

| Check | Result |
| --- | --- |
| 11 October 2026, local | Ruff passed. pytest passed 127 tests. Frontend `npm test` passed 13 tests. `npm run lint` and `npm run build` passed. These commands were not run again for this README |
| 13 October 2026, disposable Compose project `roadrisk-p12a` | One prediction was stored. The API container was recreated. The same history id, timestamp, and score remained on volume `roadrisk-p12a_roadrisk-history`. The default volume was not used |
| 13 October 2026, disposable Compose project `roadrisk-p12b` | An empty model directory was mounted. `GET /health` returned `ready: false`. `GET /model` and a valid `POST /predictions` returned HTTP 503 with `Model artifacts are not loaded`. Container logs did not include model paths or artifact filenames |
| Fresh image build | Not recorded as a passed check. The 13 October containers reused existing images |
| GitHub Actions | `.github/workflows/ci.yml` runs Ruff and pytest on Python 3.12. GitHub has not executed it from this checkout. The workflow does not run Docker and does not download the collision extract |

## Limitations

- The score is conditional on a collision that has already been reported. It is not a prediction that a crash will happen, and it is not a promise about a person, a trip, or a place.
- `LOW`, `MEDIUM`, and `HIGH` are labels for slices of the model's 2024 score distribution. They are not an official safety standard.
- The 2025 metrics are one held-out year. They were not used to choose the model, the calibration, the threshold, or the bands.
- The threshold flags most 2025 rows as fatal or serious. Precision on that year is `0.2874644131552166`.
- No hyperparameter search was run. Nothing in the evaluation measures whether a score would improve a road-safety decision.
- Police-reported injury collisions are not all crashes. Damage-only collisions are absent. Reporting practice can differ by place and year.

## Project structure

```text
apps/api/                 FastAPI application and apps/api/Dockerfile
apps/web/                 Vite dashboard and apps/web/Dockerfile
configs/data_manifest.json
docs/                     Model card, dataset card, artifact manifest, API, and phase notes
scripts/verify_frozen_artifacts.py
src/roadrisk/             Package: data, features, inference, persistence, training
tests/                    unit and integration
.github/workflows/ci.yml
compose.yaml
.env.example
.gitignore
.python-version
LICENSE
pyproject.toml
README.md
ROADMAP.md
```

`data/raw/`, `data/processed/`, `data/models/`, and `reports/` are local and gitignored. `_explore_audit.py` is a leftover local script. It is not part of the application.

## License

The code is MIT. See [LICENSE](LICENSE). The collision extract remains under the Open Government Licence v3.0 recorded in the dataset card.
