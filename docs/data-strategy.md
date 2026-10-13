# Data strategy

Status: target and source are chosen. The collision extract and codebook were downloaded on 9 October 2026 and checked against `configs/data_manifest.json`. A quality audit of that verified file is recorded in [data quality](data-quality.md). The approved predictors are in [features](features.md). Four baselines were compared on the 2024 validation split. Phase 6 then froze a calibrated model and scored 2025 once. Phase 7 maps that frozen model's 2024 scores to research bands. See [baselines](baselines.md), [phase 6](phase6.md), and [risk policy](risk-policy.md).

## Decision

RoadRisk will predict **collision severity conditional on a reported collision** (option B).

| Item | Decision |
| --- | --- |
| Intended users | Analysts and reviewers studying the circumstances of police-reported personal-injury collisions |
| Prediction unit | One STATS19 collision, identified by `collision_index` |
| Label | `collision_severity` |
| Positive class | Fatal or serious, codes `1` and `2` in the official code list |
| Product wording | Estimated probability that a reported personal-injury collision is fatal or serious, given the recorded circumstances |
| Wording that is out of scope | Probability that a collision occurs at a place and time |

Research bands (`LOW`, `MEDIUM`, `HIGH`) are a later mapping from that probability. Phase 7 set them from the 2024 score quantiles. The boundaries and the wording limits are in [risk policy](risk-policy.md).

### Why option A was not selected

Option A needs crashes divided by traffic exposure at the same place and time. The Department for Transport does publish traffic estimates:

- Street-level annual average daily flow is estimated for major-road links and for a sample of minor-road count points: [Road traffic statistics](https://roadtraffic.dft.gov.uk/about) and the [download notes](https://roadtraffic.dft.gov.uk/downloads).
- Local-authority and regional figures are vehicle-miles for a whole area and year.

Neither grain matches a STATS19 collision. A collision has coordinates and a clock time. A count point is an annual average on a link, and minor roads are only sampled. The department states that link-level and small-area traffic estimates are less robust than regional totals. Assigning the nearest count, or an authority-year total, to one collision would invent an exposure the files do not contain. Option A is therefore not the Phase 2 target. Traffic files were not downloaded.

Option C, sampling invented non-collision rows, is not used. Those scores would depend on how the non-events were created.

### Why option B is supported

The selected file is a table of personal-injury collisions already reported to the police. The official code list labels `collision_severity` as 1 Fatal, 2 Serious, and 3 Slight. That is a label on events that occurred. It does not include journeys that ended without a recorded injury collision.

## Source

| Item | Record |
| --- | --- |
| Dataset | Road Safety Open Data (STATS19 personal-injury collisions, vehicles, and casualties) |
| Publisher | Department for Transport |
| Catalogue | https://www.gov.uk/government/statistical-data-sets/road-safety-open-data |
| Catalogue history used here | Page published 25 September 2025. Last updated 30 July 2026, when final 2025 figures were added |
| Licence | Open Government Licence v3.0 |
| Licence URL | https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/ |
| Attribution | Contains public sector information licensed under the Open Government Licence v3.0. |
| data.gov.uk entry | https://www.data.gov.uk/dataset/cb7ae6f0-4be6-4935-9277-47e5ce24a11f/road-safety-data also names UK Open Government Licence (OGL) and points readers to the catalogue above |

The statistics cover personal-injury collisions on public roads that were reported to the police and recorded with STATS19. Damage-only collisions are outside the file. Contributory-factor fields are not in the open extract.

### Files accepted on 9 October 2026

Digests are SHA-256 of the bytes saved locally. They are also in `configs/data_manifest.json`.

| Role | File | Bytes | SHA-256 |
| --- | --- | --- | --- |
| Collisions | `dft-road-casualty-statistics-collision-last-5-years.csv` | 97,669,586 | `06a03c0e5504175e23ed98e3e0b4767ac61d396c073405a1bddab9339c18f948` |
| Codebook | `dft-road-casualty-statistics-road-safety-open-dataset-data-guide-2025.xlsx` | 85,112 | `51b08606ef3dad1ae5d4c8726241b022fc8e4bbdc910ef0e5cc2fb92b054fc12` |

Collision URL: https://data.dft.gov.uk/road-accidents-safety-data/dft-road-casualty-statistics-collision-last-5-years.csv

Codebook URL: https://assets.publishing.service.gov.uk/media/6ab2a71d997a4b2950cced58/dft-road-casualty-statistics-road-safety-open-dataset-data-guide-2025.xlsx

The codebook worksheet that lists codes is named `2024_code_list`.

The collision file is stored under `data/raw/`. The codebook is stored under `data/external/`. Both paths are gitignored. Re-download with:

```powershell
python -m roadrisk.data download --manifest configs/data_manifest.json
python -m roadrisk.data verify --manifest configs/data_manifest.json --inspect-header
```

`verify` fails if a required file is missing or the digest differs. It does not rewrite rows.

### Measured coverage of this download

These counts were read from the collision file after the download. They describe that file. They are not model metrics.

| `collision_year` | Rows |
| --- | --- |
| 2021 | 101,087 |
| 2022 | 106,004 |
| 2023 | 104,258 |
| 2024 | 100,927 |
| 2025 | 101,525 |
| Total | 513,801 |

The header has 44 columns. `collision_index` did not repeat in this file (513,801 distinct values).

### Files not accepted

| File | Reason |
| --- | --- |
| Collisions, 1979 to latest (about 1.5 GB) | Larger than the modeling window, and it repeats the five years above |
| Vehicle and casualty extracts | A join would repeat each collision once per vehicle or casualty. The prediction unit is the collision |
| Provisional mid-year files | The catalogue describes them as unvalidated. Final annual files are the selected vintage |
| Traffic count extracts | Grain does not support option A for a single collision |

## Column contract

Required columns are the ones the schema check demands. They were present in the downloaded header. Codes below are from the codebook, not from a trained model.

| Canonical use | Source column | Note |
| --- | --- | --- |
| Event id | `collision_index` | Unique in the downloaded file. The codebook says it joins to vehicle and casualty tables |
| Split key | `collision_year` | Also `date` and `time` |
| Coordinates | `longitude`, `latitude` | Codebook: null when unknown. Nulls are kept at this stage |
| Admin area | `local_authority_ons_district` | `lsoa_of_accident_location` is England and Wales only, so it is not required |
| Label | `collision_severity` | 1 Fatal, 2 Serious, 3 Slight |
| Road | `road_type`, `speed_limit`, `road_surface_conditions` | Speed values the codebook calls valid on public highways are 20, 30, 40, 50, 60, and 70 |
| Junction | `junction_detail`, `junction_control`, `pedestrian_crossing` | Historic twin columns exist and are not required |
| Conditions | `light_conditions`, `weather_conditions`, `urban_or_rural_area` | Weather is a reported category |

There is no visibility distance and no traffic volume on this table.

### Excluded from the default feature set

These columns are on the collision extract. Using them as predictors would leak the outcome or the reporting process. `require_features_exclude_leakage` rejects them.

| Column | Reason |
| --- | --- |
| `collision_severity` | Label |
| `number_of_vehicles` | Count produced by the collision |
| `number_of_casualties` | Count produced by the collision |
| `did_police_officer_attend_scene_of_accident` | Post-event operational field |
| `enhanced_severity_collision` | Finer severity scale, introduced where collected in 2023. The codebook name is `enhanced_collision_severity` |
| `collision_injury_based` | Flags injury-based reporting versus the older severity system |
| `collision_adjusted_severity_serious` | Adjustment figure now stored on the row. The codebook name is `collision_adjusted_serious` |
| `collision_adjusted_severity_slight` | Adjustment figure. The codebook name is `collision_adjusted_slight` |

The catalogue says injury-based reporting changed recorded severity for some police forces, and that adjustment figures now sit in the main tables. The audit measured those fields and did not treat them as the label. `enhanced_severity_collision` is populated only on injury-based rows and uses a finer serious scale (codes 5, 6, and 7). The adjustment columns are numeric weights: every fatal row is 0 and 0, and every other row sums to 1. Those weights were not applied. The recorded codes 1, 2, and 3 remain the modelling label, with the alternatives still open. See [data quality](data-quality.md).

The header names and the codebook names differ for the enhanced and adjusted fields. Validation follows the CSV header, because that is the file the digest covers.

## Splits

Named from `collision_year` in the downloaded extract. Nothing has been scored.

| Split | Years | Role |
| --- | --- | --- |
| Training | 2021–2023 | Fit later pipelines and cross-validation |
| Validation | 2024 | Model choice and thresholds |
| Test | 2025 | One later score, after the choice is frozen |

The verified extract contains only these five years, so every row falls in one split. Counts and the share of codes 1 and 2 in each split are in [data quality](data-quality.md). Those shares describe reported collisions. They are not a score and they are not the probability that a collision occurs.

`local_authority_district` is coded `-1` on 513,607 of 513,801 rows. The codebook labels that code "Code deprecated". It is excluded from predictors and from Phase 7 area summaries. `local_authority_ons_district` remains conditional: it is an administrative area code, not an approved feature, and the feature table does not emit it. Phase 7 groups recorded collisions by the approved `urban_or_rural_area` field.

## Feature contract

Version 1 is in [features](features.md). Nineteen circumstance fields are approved, including hour, weekday, month, and season derived from the collision timestamp. Latitude and longitude are approved. Grid references, police force, road numbers, and carriageway hazards are conditional and are not emitted. The target, adjustment weights, casualty and vehicle counts, identifiers, and historic schema twins are excluded.

`python -m roadrisk.features build` writes the gitignored table from the verified CSV. The build does not fit an encoder. 2025 is labelled `test` and is not used to choose columns.

## Storage rules

- `data/raw/` receives the publisher collision file unchanged.
- `data/external/` receives the codebook from the same catalogue.
- `data/processed/` receives the feature table from `python -m roadrisk.features build`. That output is gitignored.
- `data/synthetic/` is unused. Test rows live in `tests/fixtures/synthetic/` and are labeled synthetic.
- `data/models/` is unused.

Reported metrics, when they exist, use the real test year only. Synthetic fixtures never supply those metrics.

## Evaluation that led here

| Option | Question | Feasibility |
| --- | --- | --- |
| A. Exposure-based risk | How often collisions occur per unit of traffic | Official traffic estimates exist, at link-year or authority-year grain. They do not match a collision's place and time. Not selected |
| B. Severity given a collision | If a personal-injury collision is reported, how likely is it to be fatal or serious | Supported by the collision table and the code list. Selected |
| C. Case-control sample | Relative score against invented non-collision rows | Rejected. The probability would depend on the sampling design |

Other catalogs considered in Phase 1 (US Accidents, NYC collisions, FARS) were not downloaded. The UK open file supports option B under a licence that allows a public repository to describe and retrieve it.
