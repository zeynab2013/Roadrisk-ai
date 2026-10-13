# Dataset card

Status: local record of the collision extract used by RoadRisk. Publisher, catalogue, and licence statements below are copied from [`configs/data_manifest.json`](../configs/data_manifest.json) and [data strategy](data-strategy.md). The official catalogue and licence pages were not re-fetched for this card. Fresh external verification is outstanding.

The code in this repository is MIT, in [`LICENSE`](../LICENSE) and `pyproject.toml`. That licence does not replace the data licence.

## Recorded source

| Item | Recorded value |
| --- | --- |
| Publisher | Department for Transport |
| Dataset name in the manifest | Road Safety Open Data |
| Collision file | `dft-road-casualty-statistics-collision-last-5-years.csv` |
| Collision URL | https://data.dft.gov.uk/road-accidents-safety-data/dft-road-casualty-statistics-collision-last-5-years.csv |
| Catalogue URL | https://www.gov.uk/government/statistical-data-sets/road-safety-open-data |
| Catalogue note in the manifest | Catalogue page last updated 30 July 2026, when final figures for 2025 were added. The data strategy also records the page as published 25 September 2025. Those dates were not re-checked here |
| Coverage recorded for this file | `collision_year` 2021 through 2025 |
| Data rows | `513801` |
| File size | `97669586` bytes |
| SHA-256 | `06a03c0e5504175e23ed98e3e0b4767ac61d396c073405a1bddab9339c18f948` |
| Retrieval date | `2026-10-09` |
| Data licence name | Open Government Licence v3.0 |
| Data licence URL | https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/ |
| Attribution recorded in the manifest | Contains public sector information licensed under the Open Government Licence v3.0. |

The manifest also records the codebook `dft-road-casualty-statistics-road-safety-open-dataset-data-guide-2025.xlsx`, 85,112 bytes, SHA-256 `51b08606ef3dad1ae5d4c8726241b022fc8e4bbdc910ef0e5cc2fb92b054fc12`. Its code-list worksheet is named `2024_code_list`. The collision file is the modeling table. The codebook is the code list used to interpret it.

Both files are gitignored under `data/raw/` and `data/external/`. `python -m roadrisk.data verify --manifest configs/data_manifest.json` fails if a required file is missing or the digest differs. It does not rewrite rows.

## What the file contains

The data strategy describes the statistics as personal-injury collisions on public roads that were reported to the police and recorded with STATS19. Damage-only collisions are outside the file. Contributory-factor fields are not in the open extract. The measured header has 44 columns. `collision_index` did not repeat: 513,801 distinct values, matching the row count.

Year counts measured from this download and recorded in [data strategy](data-strategy.md), not as model scores:

| `collision_year` | Rows |
| --- | --- |
| 2021 | 101,087 |
| 2022 | 106,004 |
| 2023 | 104,258 |
| 2024 | 100,927 |
| 2025 | 101,525 |
| Total | 513,801 |

## Intended use in this project

The prediction unit is one collision, identified by `collision_index`. The label is `collision_severity`. Codes `1` (fatal) and `2` (serious) are the positive class. Code `3` (slight) is the negative class. The question is whether a reported personal-injury collision was fatal or serious rather than slight.

The file is not used to estimate whether a collision occurs. Traffic-count extracts were not downloaded. The data strategy records that those counts are not at the grain of one collision, so joining them would invent an exposure. Invented non-collision rows are not used.

Vehicle and casualty extracts were not accepted, because a join would repeat each collision once per vehicle or casualty. The longer 1979-to-latest collision file was not accepted. Provisional mid-year files were not accepted. The manifest's publication note describes the selected vintage as the final 2025 figures.

## Target construction and split

The feature build on 9 October 2026 kept 513,801 of 513,801 rows from this digest. Rows would be dropped only when `collision_index` is blank, `collision_severity` is outside `{1, 2, 3}`, or `collision_year` is outside 2021–2025. None of those drops occurred in that build. The mapped label counts are in [features](features.md):

| Split | Years | Rows | Positive labels |
| --- | --- | --- | --- |
| Training | 2021–2023 | 311,349 | 72,653 |
| Validation | 2024 | 100,927 | 25,069 |
| Test | 2025 | 101,525 | 26,644 |

2025 is held out from feature approval, model selection, calibration, threshold choice, and research-band cuts. The 2025 positive count matches `positive_rows` in the evaluation artifact. Those label counts are not model metrics. The scored metrics are in [model card](model-card.md).

## Preprocessing and missing values

Nineteen approved fields are built from circumstances that are known when the collision is reported. The specification is version 1 in [features](features.md). Target-derived fields, casualty and vehicle counts, later geographies, and identifiers are not model inputs.

`missing` means blank or codebook `-1`. `unknown` means the codebook's own unknown code. `unexpected` means a code outside the transcribed list. Those tokens are not filled from other rows. Blank numeric inputs stay blank in the feature table. Median imputation for numeric inputs, and the categorical encoding, are fitted inside the training pipeline on 2021–2023 only.

A quality audit of the verified CSV is summarized in [data quality](data-quality.md). The generated audit files under `reports/quality/` are gitignored.

## Limitations and representativeness

- The table is police-reported personal-injury collisions. It does not represent damage-only crashes or journeys without a recorded injury collision.
- Reporting practice can differ by place and year. `police_force` was not approved as a model input because it may proxy injury-based reporting. That exclusion is recorded in the feature specification. It does not remove the underlying reporting difference from the label.
- There is no traffic-exposure denominator. Counts and rates in this file are counts of recorded collisions, not risk per vehicle or per person.
- Some approved fields are often missing or unknown. The feature table keeps those tokens. In particular, many audited `special_conditions_at_site` values are `-1` and stay `missing`. Fifty-three audited rows have no coordinate. Those findings are in the feature specification, not a new audit.
- `urban_or_rural_area` includes code `3` (unallocated). Administrative geographies were not treated as usable area keys.
- Weather and light fields are reported categories, not measurements from a weather station.
- The codebook worksheet used here is named `2024_code_list` inside the 2025 data guide. Earlier-year columns that the guide replaced were not approved.
- This card does not re-verify the publisher's current catalogue text or the Open Government Licence page. Those statements remain the values stored in the manifest on the retrieval date above.

## Related records

- [Data strategy](data-strategy.md)
- [Data quality](data-quality.md)
- [Feature specification](features.md)
- [Model card](model-card.md)
- [`configs/data_manifest.json`](../configs/data_manifest.json)
