# Collision data-quality audit

Status: measured on 9 October 2026 from the verified collision extract. The audit does not train a model, score 2025, or rewrite the CSV. The target is the severity of a reported personal-injury collision. It is not the probability that a collision occurs.

Generated files, when the command has been run, are `reports/quality/collision-audit.json` and `reports/quality/collision-audit.md`. That directory is gitignored. This page is the committed record of the run below.

## Command

From the repository root, with the package environment active:

```powershell
python -m roadrisk.data verify --manifest configs/data_manifest.json --inspect-header
python -m roadrisk.data audit --manifest configs/data_manifest.json
```

`audit` hashes the collision file before reading rows. If the file is missing, or the SHA-256 or size differs from `configs/data_manifest.json`, the command exits 1 and writes nothing. A missing required column also exits 1. Warnings in the report, including incomplete coordinates, do not change the exit status and do not edit `data/raw/`.

The implementation is `src/roadrisk/data/quality.py` (rules and counts) and `src/roadrisk/data/report.py` (JSON and Markdown). Code lists that the audit compares are transcribed in `src/roadrisk/data/codebook.py` from the 2025 data-guide worksheet `2024_code_list`. The module does not open the workbook at runtime.

Python 3.12 is not installed. The audit runs on Python 3.10.11 with the standard-library CSV reader. Pandas was not added.

## Source identity

| Item | Value |
| --- | --- |
| Manifest schema | 1 |
| File id | `collisions-last-5-years` |
| Filename | `dft-road-casualty-statistics-collision-last-5-years.csv` |
| SHA-256 | `06a03c0e5504175e23ed98e3e0b4767ac61d396c073405a1bddab9339c18f948` |
| Bytes | 97,669,586 |
| Catalogue | https://www.gov.uk/government/statistical-data-sets/road-safety-open-data |
| Audit timestamp (UTC) | 2026-10-09T09:45:37+00:00 |
| Rows | 513,801 |
| Columns | 44 |

`verify --inspect-header` on this file returned exit 0 before the audit.

## Modelling population

A row is retained only when all three rules hold:

1. `collision_index` is present.
2. `collision_severity` is 1, 2, or 3.
3. `collision_year` is 2021, 2022, 2023, 2024, or 2025.

Rows are not dropped for missing coordinates, coded-missing predictors, or adjustment weights. The audit does not impute or rewrite values.

| Result | Rows | Share |
| --- | --- | --- |
| Retained | 513,801 | 100% |
| Excluded | 0 | 0% |

No exclusion reason fired. Blank identifiers, severity values outside {1, 2, 3}, and years outside 2021–2025 were all zero.

## Target

| Item | Decision |
| --- | --- |
| Column | `collision_severity` |
| Question | Given a reported personal-injury collision, was it fatal or serious rather than slight? |
| Positive class | Code 1 Fatal, or code 2 Serious |
| Negative class | Code 3 Slight |
| Status | `supported_with_unresolved_alternatives` |

Observed codes, with no missing or unexpected severity values:

| Code | Label | Class | Rows | Share |
| --- | --- | --- | --- | --- |
| 1 | Fatal | Positive | 7,553 | 1.47% |
| 2 | Serious | Positive | 116,813 | 22.7351% |
| 3 | Slight | Negative | 389,435 | 75.7949% |
| 1 or 2 | Fatal or serious | Positive | 124,366 | 24.2051% |

The codebook labels are 1 Fatal, 2 Serious, and 3 Slight. The CSV uses those codes on every row.

### Why the target is not closed

Two related fields were measured. Neither replaces `collision_severity`.

`enhanced_severity_collision` (codebook name `enhanced_collision_severity`) uses 1 Fatal, 5 Very Serious, 6 Moderately Serious, 7 Less Serious, 3 Slight, and -1 for data missing or out of range. On this extract it is coded -1 on 204,752 rows. Within each recorded severity, those -1 rows are exactly the rows with `collision_injury_based` 0 (severity reporting). The populated rows are exactly `collision_injury_based` 1 (injury-code reporting), and they line up with the recorded code:

| Recorded severity | Enhanced value | Rows | Injury-based flag |
| --- | --- | --- | --- |
| 1 Fatal | 1 Fatal | 5,137 | 1 |
| 1 Fatal | -1 | 2,416 | 0 |
| 2 Serious | 5 Very Serious | 14,377 | 1 |
| 2 Serious | 6 Moderately Serious | 17,331 | 1 |
| 2 Serious | 7 Less Serious | 48,004 | 1 |
| 2 Serious | -1 | 37,101 | 0 |
| 3 Slight | 3 Slight | 224,200 | 1 |
| 3 Slight | -1 | 165,235 | 0 |

There is no row where a populated enhanced code contradicts the recorded fatal, serious, or slight group. The fields are still not interchangeable: the enhanced serious scale is three codes rather than code 2, and it is absent on every severity-reporting row.

`collision_adjusted_severity_serious` and `collision_adjusted_severity_slight` (codebook names `collision_adjusted_serious` and `collision_adjusted_slight`) have empty code and format cells in the guide. They are weights, not class labels. Every fatal row is 0 and 0 (7,553 rows). Every non-fatal row sums to 1. Of the serious rows, 112,245 are one-hot and 4,568 are fractional. Of the slight rows, 315,857 are one-hot and 73,578 are fractional. No weight was blank, non-numeric, or outside that pattern. The weights were not turned into a label.

Alternatives left open:

| Alternative | Why it was not selected |
| --- | --- |
| Recorded `collision_severity`, codes 1 and 2 versus 3 | Used as the modelling label because it is complete and matches the codebook classes. Injury-based reporting still changed how some forces record serious and slight, so this is not a claim that the series is homogeneous |
| Enhanced scale as the label | Missing on 204,752 rows, and serious is split into codes 5, 6, and 7 |
| Adjusted weights as the label | Numeric weights. Fatal rows are both zero. Applying them would change the target. They were not applied |

## Temporal split

The file supports the planned split. No row has a missing or invalid year, and no year falls outside 2021–2025.

| Split | Years | Rows | Codes 1 or 2 | Share |
| --- | --- | --- | --- | --- |
| Training | 2021–2023 | 311,349 | 72,653 | 23.3349% |
| Validation | 2024 | 100,927 | 25,069 | 24.8387% |
| Test | 2025 | 101,525 | 26,644 | 26.2438% |

| Year | Rows | Fatal | Serious | Slight |
| --- | --- | --- | --- | --- |
| 2021 | 101,087 | 1,474 | 21,284 | 78,329 |
| 2022 | 106,004 | 1,602 | 23,333 | 81,069 |
| 2023 | 104,258 | 1,522 | 23,438 | 79,298 |
| 2024 | 100,927 | 1,502 | 23,567 | 75,858 |
| 2025 | 101,525 | 1,453 | 25,191 | 74,881 |

Dates parse as DD/MM/YYYY, times parse as HH:MM, and the date year matches `collision_year` on every row. Blank dates and blank times are zero. The test year was counted and was not scored.

## Other measured checks

| Check | Result |
| --- | --- |
| Duplicate `collision_index` | 0 |
| Blank `collision_index` | 0 |
| Same id with different row contents | 0 |
| Latitude or longitude missing | 53 rows. Easting or northing is missing on the same count. These rows stay in the population |
| Non-numeric coordinates or grid values | 0 |
| Coordinate origin (0, 0) | 0 |
| Outside the audit window | 0 |

The latitude window is 49.5 to 61.1 and the longitude window is -8.8 to 2.2. Observed numeric coordinates run from latitude 49.91221 to 60.500008 and longitude -7.486852 to 1.759829. The grid window is easting 0 to 700,000 and northing 0 to 1,300,000. A point outside either window would be reported as suspicious and would not be deleted. None were outside.

Transcribed code lists found no unexpected codes. Coded `-1` on those fields is the codebook missing value, not an unexpected code. Examples: `speed_limit` is 20, 30, 40, 50, 60, or 70, plus 3 rows of `-1` and no `99`. `urban_or_rural_area` is Urban (345,314), Rural (168,429), Unallocated (50), and `-1` (8). Unallocated is code 3 in the codebook. It is unusual and allowed.

`local_authority_district` is coded `-1` on 513,607 rows (99.9622%). The codebook label for that code is "Code deprecated". The other 194 rows use 14 district codes. This column is administrative. It is not a predictor. The ONS district column is the area code to consider later.

`speed_limit` code 99, "unknown (self reported)", is in the codebook and does not appear in this extract.

## Feature-risk inventory

The inventory classifies columns. It does not approve them as model inputs. Phase 4 has to choose a subset.

| Role | Columns |
| --- | --- |
| Potential predictors | `location_easting_osgr`, `location_northing_osgr`, `longitude`, `latitude`, `date`, `day_of_week`, `time`, `first_road_class`, `road_type`, `speed_limit`, `junction_detail`, `junction_control`, `second_road_class`, `pedestrian_crossing`, `light_conditions`, `weather_conditions`, `road_surface_conditions`, `special_conditions_at_site`, `urban_or_rural_area`, `trunk_road_flag` |
| Identifiers | `collision_index`, `collision_ref_no` |
| Split key | `collision_year` |
| Target | `collision_severity` |
| Post-outcome | `number_of_vehicles`, `number_of_casualties`, `did_police_officer_attend_scene_of_accident` |
| Target-derived | `enhanced_severity_collision`, `collision_injury_based`, `collision_adjusted_severity_serious`, `collision_adjusted_severity_slight` |
| Domain decision | `local_authority_highway_current`, `first_road_number`, `junction_detail_historic`, `second_road_number`, `pedestrian_crossing_human_control_historic`, `pedestrian_crossing_physical_facilities_historic`, `carriageway_hazards_historic`, `carriageway_hazards` |
| Administrative | `police_force`, `local_authority_district`, `local_authority_ons_district`, `local_authority_highway`, `lsoa_of_accident_location` |

Post-outcome and target-derived columns stay out of the feature set. Historic twins of current fields need an explicit choice before use, because they overlap the current columns. High-cardinality identifiers and area codes are not predictors by default.

## Checks that did not run

- Code lists are not transcribed for `police_force`, `local_authority_district`, the historic junction and crossing fields, or `carriageway_hazards_historic`. Their frequencies were counted. They were not compared with the workbook.
- `local_authority_ons_district`, `local_authority_highway`, `local_authority_highway_current`, `first_road_number`, `second_road_number`, and `lsoa_of_accident_location` exceeded the 50-value frequency cap, so a code-list comparison was not attempted.
- Latitude, longitude, easting, northing, date, and time use range and parse checks instead of a code list.
- No model was scored, including on 2025.

## Limitations

- The population rules accept every row in this file. That is a measurement, not a decision that every column is usable.
- The Great Britain windows are plausibility bounds in the audit, not an official boundary file.
- Coordinate gaps were counted, not inspected row by row.
- Injury-based reporting means the recorded serious and slight classes are not a single reporting system across forces. The audit does not correct that.
- Adjustment weights were described, not applied.
- The dashboard does not load this audit.
