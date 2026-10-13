# RoadRisk roadmap

Phases 1 through 9 are in the repository for the definitions of done recorded below. Later phases are a plan. Do not treat a later phase as done because this file names its files.

Each phase assumes the previous phase's definition of done is met. Dates are not scheduled.

## Phase 1 — Architecture and project foundation

**Goal.** Give a reviewer a clear design, an honest status, and a Python package boundary, without pretending the product exists.

**Deliverables.**

- README with current status
- This roadmap
- Architecture and data-strategy documents
- `.gitignore`, MIT licence, `pyproject.toml`
- Empty data directories and a package that exposes `__version__`

**Main files.**

- `README.md`
- `ROADMAP.md`
- `docs/architecture.md`
- `docs/data-strategy.md`
- `pyproject.toml`
- `src/roadrisk/__init__.py`
- `tests/unit/test_package.py`
- `data/README.md`

**Tests.** `tests/unit/test_package.py` checks the public version.

**Definition of done.**

- A new reader can see what is planned and what is absent.
- No dataset, model binary, metric, API, or UI is presented as real.
- `pytest` and `ruff check src tests` pass in a virtual environment.

**Dependencies.** None.

## Phase 2 — Dataset, data checks, and dashboard shell

**Status.** Complete for the definition below. Python 3.12 and pandas were still unavailable when Phase 3 ran, so the quality audit uses the standard library.

**Goal.** Lock the prediction question, record a real DfT extract, check its digest and header, and stand up an honest dashboard shell.

**Deliverables.**

- Target decision in `docs/data-strategy.md`: severity given a reported collision
- `configs/data_manifest.json` with source URLs, licence, byte sizes, and SHA-256 digests
- Download, verify, header, duplicate-id, and leakage checks
- React dashboard shell that states what is unavailable
- Official logo copied into `frontend/public/brand/roadrisk-logo.png`

**Main files.**

- `docs/data-strategy.md`
- `docs/frontend.md`
- `configs/data_manifest.json`
- `src/roadrisk/config.py`
- `src/roadrisk/logging.py`
- `src/roadrisk/data/`
- `frontend/`
- `tests/unit/test_schema.py`, `test_manifest.py`, `test_integrity.py`, `test_file_status.py`
- `tests/fixtures/synthetic/`

**Tests.**

- Manifest parsing, including a rejected digest
- SHA-256 match and mismatch
- Missing file, empty file, missing column, duplicate id
- A leakage column cannot be proposed as a feature
- Frontend navigation, disabled prediction, and absence of invented counts
- The official extract is checked only when the gitignored file is already on disk

**Definition of done.**

- The target, licence, and column contract are written from the publisher's catalogue, codebook, and downloaded header.
- Required files can be verified by digest. A missing or changed file fails the command.
- No estimator has been fit, and the dashboard shows no invented metrics.
- `pytest`, `ruff check src tests`, `npm test`, `npm run lint`, and `npm run build` pass in the environments used for this phase.

**Dependencies.** Phase 1.

## Phase 3 — EDA and data quality

**Status.** Complete for the definition below. The audit module and fixture tests are in the repository. The generated JSON and Markdown for the real extract are written under `reports/quality/` and are gitignored. Python 3.12 is not installed, so this phase did not add pandas.

**Goal.** Measure the chosen extract and write the findings that feature engineering is allowed to use.

**Deliverables.**

- `python -m roadrisk.data audit` reads the already verified collision CSV and writes JSON and Markdown
- Measured coverage, severity counts, exclusion rules, coordinate checks, and a feature-risk inventory
- [docs/data-quality.md](docs/data-quality.md), which records both the findings and the unresolved severity-field choice

Notebooks were not added. The tested module is the record, and the command can be re-run.

**Main files.**

- `src/roadrisk/data/quality.py`
- `src/roadrisk/data/report.py`
- `src/roadrisk/data/codebook.py`
- `tests/unit/test_quality.py`
- `docs/data-quality.md`

**Tests.** Synthetic fixtures cover the binary label, bad severity codes, duplicate identifiers, invalid years, a missing column, bad dates and coordinates, identical inputs, a checksum failure, and adjusted fields that are not a class label.

**Definition of done.**

- The report distinguishes measured facts from modeling choices.
- Outcome columns called out in Phase 2 are confirmed against the file.
- No model comparison is included.

**Dependencies.** Phase 2.

## Phase 4 — Feature engineering

**Status.** Complete for the definition below. The feature contract and the standard-library transforms are in the repository. The generated table is gitignored under `data/processed/`. Python 3.12 and scikit-learn are not installed, so this phase does not fit or pickle a pipeline. Historical crash counts were not added.

**Goal.** Lock the predictors that may enter a later model, and build them without using the target or the test year to decide columns.

**Deliverables.**

- Approved, conditional, and excluded fields in [docs/features.md](docs/features.md)
- Hour, weekday, month, and season from the collision timestamp
- A temporal split that assigns 2025 to test only
- `python -m roadrisk.features build` for the verified collision extract

**Main files.**

- `src/roadrisk/features/spec.py`
- `src/roadrisk/features/transform.py`
- `src/roadrisk/features/split.py`
- `src/roadrisk/features/build.py`
- `docs/features.md`
- `tests/unit/test_features.py`

**Tests.** Synthetic fixtures cover the label mapping, the allowlist, forbidden fields, datetime parts, missing codes, the historic junction schema, split boundaries, a checksum failure, and identical outputs for identical inputs.

**Definition of done.**

- Model inputs are an explicit allowlist. The target and the adjustment fields are not on it.
- The same source file produces the same feature CSV.
- 2025 stays in the test split, and no model is scored.

**Dependencies.** Phases 2 and 3.

## Phase 5 — Baseline models

**Status.** Complete for the definition below. Four untuned baselines were fit on 2021–2023 and compared on 2024. The provisional choice is histogram gradient boosting. 2025 was held out and not scored. Cross-validation and threshold search were not run. The recorded scores are in [docs/baselines.md](docs/baselines.md).

**Goal.** Compare untuned baselines on the same splits so later tuning has a reference.

**Deliverables.**

- `DummyClassifier`, logistic regression, random forest, and `HistGradientBoostingClassifier`
- Training-only preprocessing inside each scikit-learn `Pipeline`
- A comparison written by `python -m roadrisk.training train`

**Main files.**

- `src/roadrisk/training/pipelines.py`
- `src/roadrisk/training/run.py`
- `src/roadrisk/training/__main__.py`
- `docs/baselines.md`
- `tests/unit/test_training.py`

**Tests.** Synthetic frames check the label, the allowlist, the 2025 holdout, training-only imputation, unseen categories, metrics, repeatable logistic scores, and artifact reload.

**Definition of done.**

- All four baselines share the Phase 4 feature contract and the temporal split.
- The real test period has not been scored.
- The comparison table is generated by code, not typed in by hand.

**Dependencies.** Phase 4.

## Phase 6 — Evaluation and model selection

**Status.** Complete for calibration, threshold selection, a frozen configuration, and one 2025 score. The model is histogram gradient boosting with sigmoid calibration and threshold 0.15. The record is [docs/phase6.md](docs/phase6.md). A hyperparameter search was not run, and no cost ratio was invented. 2025 was not used to choose the model or the threshold.

**Goal.** Choose one model and one operating point with metrics that reflect a rare positive class and unequal error costs.

**Deliverables.**

- Validation metrics: precision, recall, F1, ROC-AUC, PR-AUC, confusion matrix, Brier score, calibration curve
- A short search over hyperparameters for the two strongest baselines, inside the training period
- One frozen choice, with a written reason
- One score of the test period after the choice is frozen
- A version directory under `data/models/` matching the metadata schema in the architecture doc

**Main files.**

- `src/roadrisk/evaluation/metrics.py`
- `src/roadrisk/evaluation/compare.py`
- `src/roadrisk/training/tune.py`
- `docs/model-selection.md`
- `tests/unit/test_metrics.py`

**Tests.** Metric helpers match known values on a hand-built vector. Artifact metadata fails validation if the target definition or threshold policy is missing.

**Definition of done.**

- The selection metric is stated (expected: PR-AUC, together with recall at the chosen precision or cost).
- Accuracy is present and is not the reason for the choice.
- The relative cost of a false negative and a false positive is an explicit assumption.
- XGBoost or LightGBM appears only if this phase records a validation gap that justifies it.

**Dependencies.** Phase 5.

## Phase 7 — Explainability and risk analysis

**Status.** Complete for the definition below. The frozen Phase 6 pipeline is unchanged. Research bands are the 2024 validation quantiles 0.196970155937929 and 0.3126165522731136. The binary threshold remains 0.15. The 2025 evaluation was not used and was not rewritten. The record is [docs/risk-policy.md](docs/risk-policy.md).

**Goal.** Attach a probability, a research band, and an explanation to the frozen model, and summarize recorded collisions by a supported geographic field without ranking small counts as dangerous.

**Deliverables.**

- `LOW`, `MEDIUM`, and `HIGH` boundaries stored in `data/models/phase7-v1/risk-bands.json`, derived from the 2024 score distribution
- Local missing-value sensitivities for one reported collision, separate from a global permutation summary
- An urban/rural table with a minimum support rule
- Policy text that a later API can show with the score

**Main files.**

- `src/roadrisk/inference/risk.py`
- `src/roadrisk/inference/explain.py`
- `src/roadrisk/inference/groups.py`
- `src/roadrisk/inference/artifacts.py`
- `docs/risk-policy.md`
- `tests/unit/test_phase7.py`

**Tests.**

- Boundary probabilities fall into the expected band, including the exact cuts
- Bands change when the stored boundaries change
- A 2025 frame is rejected before category scores are computed
- A group below the support minimum is omitted from `supported_groups`
- Protected Phase 5 and Phase 6 files stay byte-identical after a read-only load

**Definition of done.**

- The same functions the tests call are the functions the API will call: `explain_frame`, `assign_category`, `load_risk_bands`, and `summarize_groups`.
- The policy text can be read without opening a notebook.
- No band boundary is a hard-coded 0.33 or 0.66 default.

**Dependencies.** Phase 6.

## Phase 8 — Prediction API

**Status.** Complete for the definition below. FastAPI serves the frozen Phase 6 pipeline and the Phase 7 band file. Routes are `GET /health`, `GET /model`, and `POST /predictions`. There is no batch route. Prediction history and the dashboard were later phases. The record is [docs/api.md](docs/api.md).

**Goal.** Serve the frozen artifact over HTTP without putting model code in the route handlers.

**Deliverables.**

- FastAPI application
- `GET /health`, `GET /model`, `POST /predictions`
- Pydantic request and response models limited to the artifact's features
- Response fields: probability, risk level, model version, threshold policy

**Main files.**

- `apps/api/main.py`
- `apps/api/routes/predictions.py`
- `apps/api/schemas.py`
- `src/roadrisk/inference/service.py`
- `tests/integration/test_api.py`

**Tests.** The test client scores a fixture artifact built in the test from synthetic data. Health and model routes return the fixture version. An unknown field is rejected.

**Definition of done.**

- Routes call `inference.service` and do not fit or transform data themselves.
- The library still imports without FastAPI installed, aside from the API extra.
- The fixture model is labeled so it cannot be confused with the Phase 6 artifact.

**Dependencies.** Phase 7.

## Phase 9 — Database and prediction history

**Status.** Complete for the definition below. SQLAlchemy 2 stores each accepted prediction in SQLite after scoring. `GET /predictions` returns those rows oldest-first, then by id. The default file is `data/roadrisk.sqlite3`, overridden by `ROADRISK_DATABASE_URL`. The inference service does not import the database layer. The record is [docs/api.md](docs/api.md).

**Goal.** Persist each accepted prediction and list it back.

**Deliverables.**

- SQLAlchemy 2 models for prediction history
- SQLite by default through `ROADRISK_DATABASE_URL`
- `GET /predictions` with a simple time order
- A migration approach if the schema is no longer created in one step

**Main files.**

- `src/roadrisk/persistence/models.py`
- `src/roadrisk/persistence/repository.py`
- `apps/api/routes/history.py`
- `tests/integration/test_history.py`

**Tests.** A prediction through the API is stored and returned by the history route. The test database is temporary.

**Definition of done.**

- The prediction service still does not import the database layer. The API writes history after scoring.
- No database file is committed.
- Connection settings come from the environment.

**Dependencies.** Phase 8.

## Phase 10 — Professional dashboard

**Status.** Complete for the definition below. `apps/web` is the only dashboard. It calls `GET /health`, `GET /model`, `POST /predictions`, `GET /predictions`, and `GET /area-summaries`. The area route reads the saved Phase 7 urban/rural summary when that file matches the loaded decision. The UI does not score rows. The record is [docs/frontend.md](docs/frontend.md).

**Goal.** Turn the Phase 2 shell into a client that scores through the API, shows history, and shows area summaries when those endpoints exist. The shell and logo started in `frontend/` and now live in `apps/web`.

**Deliverables.**

- Vite, React, and TypeScript app in `apps/web`
- Views for a prediction, history, the active model card, and high-risk areas when that endpoint exists
- Typed client for the API responses
- Empty, error, and loading states for each view

**Main files.**

- `apps/web/`
- Any new read-only API route required for the area table

**Tests.**

- API tests still cover the contract the UI uses
- A documented manual pass of the main flows, plus a browser check of scoring, history, and the model view

**Definition of done.**

- The UI contains no scoring math and no database credentials.
- The displayed model version matches `GET /model`.
- A failed request is visible as an error state.

**Dependencies.** Phases 8 and 9. The area view also depends on Phase 7.

## Phase 11 — Testing and quality

**Status.** Complete for the definition below. `.github/workflows/ci.yml` installs `.[dev,ml,api]` on Python 3.12 and runs `python -m ruff check src tests apps` and `python -m pytest`. Those are the local commands. GitHub has not executed the workflow in this checkout. The dashboard checks stay local. Request failures carry `X-Correlation-ID` and do not log the request body. The record is [docs/api.md](docs/api.md).

**Goal.** Make the checks that already exist run the same way locally and on pull requests.

**Deliverables.**

- GitHub Actions workflow for Ruff and pytest
- Coverage focused on features, metrics, risk levels, and the API
- Logging review so request failures include a correlation id and do not log payloads that are irrelevant to have in logs

**Main files.**

- `.github/workflows/ci.yml`
- `tests/` additions where a branch is untested

**Tests.** The workflow installs `.[dev,ml,api]` and runs `python -m ruff check src tests apps` and `python -m pytest`. It does not download the dataset. GitHub has not run the workflow.

**Definition of done.**

- A pull request cannot merge with a failing lint or test job once branch protection is turned on.
- Synthetic and real evaluation data are still separated in the tests.

**Dependencies.** Phases 4 through 9 at the layers those tests cover. The workflow can land as soon as the suite is stable, and it should be updated when the dashboard job is worth adding.

## Phase 12 — Docker and deployment

**Status.** PASS WITH NOTES. `apps/api/Dockerfile`, `apps/web/Dockerfile`, and `compose.yaml` are in the repository. The dashboard is published on port 8080 and the API on port 8000. `data/models` is mounted read-only, and SQLite history uses the `roadrisk-history` volume. The image definitions exclude the dataset, secrets, virtual environments, and frozen model files. PostgreSQL is a `ROADRISK_DATABASE_URL` change, not a Compose service. Phase 11 CI does not run Docker. On 11 October 2026, Ruff, pytest (127 passed), frontend tests (13 passed), frontend lint, and the frontend production build passed. On 13 October 2026, two disposable Compose projects were checked with the existing images. No image rebuild was performed. A history-persistence test passed: the same prediction record survived API container recreation with the disposable named volume preserved. A missing-artifact test passed: `GET /health` returned `ready: false`, `GET /model` returned HTTP 503, and a valid `POST /predictions` returned HTTP 503 with the detail `Model artifacts are not loaded`. Logs did not expose model paths or artifact filenames. The default project and its history volume were preserved. These tests do not establish that a fresh image build or a GitHub Actions workflow has passed.

**Goal.** Run the API and dashboard from containers with environment-based configuration.

**Deliverables.**

- API image
- Web image
- Compose file for local use
- `.env.example` matching the variables the processes actually read
- Optional PostgreSQL service documented as a URL change

**Main files.**

- `Dockerfile` or `apps/api/Dockerfile` and `apps/web/Dockerfile`
- `compose.yaml`
- `.env.example`

**Tests.** A container smoke test: `/health` returns success and `/model` reports the mounted artifact version.

**Definition of done.**

- Images build without copying `.env`, `data/raw`, or local virtual environments.
- The model artifact is mounted or downloaded by a documented step, not baked in from a laptop path.
- SQLite remains valid for the single-container demo.

**Dependencies.** Phases 8 through 11.

## Phase 13 — Documentation and GitHub release

**Goal.** Publish the project so a reviewer can run it and can see exactly what the model is allowed to claim.

**Deliverables.**

- Updated README with the commands that work
- Model card: target, data vintage, metrics on the test period, threshold policy, limits
- Dataset card pointing at the publisher and the licence
- API usage taken from the live OpenAPI schema
- A GitHub release tagged at the commit that produced the artifact metadata

**Main files.**

- `README.md`
- `docs/model-card.md`
- `docs/dataset-card.md`

**Tests.** The release commit is the same commit recorded in `metadata.json`. Documentation examples are the requests the integration tests already send.

**Definition of done.**

- The README claims only features that run from a clean checkout plus the documented data step.
- Metrics in the model card match the artifact file.
- The release notes state the target in the wording Phase 2 locked.

**Dependencies.** Phases 2 through 12.

## Working agreements for every phase

- Prefer a small module over a new framework.
- Add a dependency in the phase that imports it, and record why.
- Keep reported scores off synthetic data.
- Update `docs/architecture.md` when a boundary changes.
- Leave Git history free of dataset dumps, model binaries, and secrets.
