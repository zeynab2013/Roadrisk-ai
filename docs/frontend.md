# Frontend

The dashboard is the Vite application in `apps/web`. It was moved there from the Phase 2 shell in `frontend/`. There is one UI. It does not import the Python package, score collisions, or read SQLite.

## Stack

Locked in `apps/web/package-lock.json` from the ranges in `apps/web/package.json`:

| Package | Role |
| --- | --- |
| React 19 and React Router 7 | Pages and navigation |
| TypeScript strict mode | Component and client types |
| Vite 8 | Dev server and production build |
| Tailwind CSS 4 | Design tokens and layout |
| A small shadcn-style layer | `cn`, `Button`, and `Card` (`class-variance-authority`, `clsx`, `tailwind-merge`, Radix Slot) |
| Lucide | Icons |
| Vitest, Testing Library, ESLint | Tests and lint |

IBM Plex Sans is loaded from `@fontsource/ibm-plex-sans`. Recharts is not installed. Area results are a table, not a map, because the saved summary is urban or rural class rather than a coordinate grid.

Node.js used for the checks in this phase: 24.20.0.

## Brand

`apps/web/public/brand/roadrisk-logo.png` is the supplied lockup, copied from `frontend/public/brand/roadrisk-logo.png` without resizing or recoloring. It is a 1024×1024 PNG in 24-bit RGB, so the white field is opaque. The sidebar and the small-screen header show that full image at its original aspect ratio.

It is not used as a favicon. The artwork includes the wordmark and a large clear area, and cutting an icon out of it would crop the lockup.

## Run

Start the API first, from the repository root:

```powershell
.\.venv312\Scripts\python.exe -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

Then, from `apps/web`, with Node.js on `PATH`:

```powershell
npm install
npm test
npm run lint
npm run build
npm run dev
```

`npm run dev` prints a local URL, normally `http://127.0.0.1:5173`. The API allows that origin and `http://localhost:5173`. Set `ROADRISK_CORS_ORIGINS` on the API if the page is served from another origin.

`VITE_API_BASE_URL` selects the API for `npm run dev` and for `npm run build`. When it is unset, the client uses `http://127.0.0.1:8000`, which matches the command above. Copy `apps/web/.env.example` to `apps/web/.env` only when a different URL is required. Restart `npm run dev` after changing it. Vite reads that variable when it builds the bundle, so changing it in a running container does not retarget an image that was already built.

`apps/web/public/config.js` may set `window.__ROADRISK_API_BASE_URL__`. When that property is present, it overrides `VITE_API_BASE_URL`. The Compose web container rewrites the file at startup. The default value is `/api`, and nginx forwards that prefix to the API service. An empty string means the page origin. The local file does not set the property.

## Pages

| Route | What it shows |
| --- | --- |
| `/` | Whether `GET /health` says the API is ready, and the model identity from `GET /model` when it is |
| `/predict` | One collision, sent to `POST /predictions`. Probability, class, and risk band are the response fields |
| `/history` | `GET /predictions`. Empty when the API has no rows |
| `/model` | The `GET /model` body, including the threshold and band cuts |
| `/areas` | `GET /area-summaries`. Saved urban/rural model-score shares, not a safety ranking |

The prediction form sends the 19 approved features. Blank numbers and the Missing choice are JSON `null`. The choice `unknown` is the pipeline token, used only where the codebook has an unknown code. Category labels are shown only when the feature specification names them. Other codes stay `Code N`.

The browser does not apply the threshold or the band cuts. It displays `binary_threshold` from the prediction or model response.

## Tests

`npm test` mocks `fetch`. Those fixtures are labeled in the test file and are not a fallback in `src/lib/api.ts`. A failed request stays an error. The production client does not invent a probability.

There is no browser-automation suite in the repository. The Phase 10 check used the IDE browser against the local API and this dev server. Repeat that pass by starting both processes, then opening Overview, scoring one collision, refreshing History, and opening Model and Areas. Do not submit the 2025 feature table.
