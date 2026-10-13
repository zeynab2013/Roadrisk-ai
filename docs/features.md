# Feature specification

Status: version 1. The prediction target remains `collision_severity`. Fatal and Serious (codes 1 and 2) map to 1. Slight (code 3) maps to 0. The question is whether a reported personal-injury collision was fatal or serious. It is not the probability that a collision occurs.

The prediction point is after the collision has been reported and its initial circumstances recorded, and before the final severity outcome is known. A field is approved only when it is a circumstance of that report. Target-derived fields, casualty and vehicle counts, later geographies, and identifiers are not model inputs.

Category tokens in the feature table are fixed from the 2025 data-guide worksheet `2024_code_list`. Learned imputation and encoding are fitted later, on 2021–2023 only, inside the training pipelines described in [baselines](baselines.md).

## Commands

```powershell
python -m roadrisk.data verify --manifest configs/data_manifest.json --inspect-header
python -m roadrisk.features build --manifest configs/data_manifest.json
```

`build` refuses to run unless the collision file matches the manifest. It writes gitignored files:

- `data/processed/collision-features-v1.csv`
- `data/processed/collision-features-v1.meta.json`

A checksum or schema failure exits 1. The raw CSV is not modified. The build on 9 October 2026 retained 513,801 of 513,801 rows from digest `06a03c0e5504175e23ed98e3e0b4767ac61d396c073405a1bddab9339c18f948`.

| Split | Years | Rows | Positive labels |
| --- | --- | --- | --- |
| Training | 2021–2023 | 311,349 | 72,653 |
| Validation | 2024 | 100,927 | 25,069 |
| Test | 2025 | 101,525 | 26,644 |

Those positive counts are the mapped label. They are not a model score. 2025 is not used to choose features.

Rows are dropped only when `collision_index` is blank, `collision_severity` is outside {1, 2, 3}, or `collision_year` is outside 2021–2025. Missing predictors stay in the row as `missing`, `unknown`, or a blank number.

## Approved model inputs

`missing` means blank or codebook `-1` (data missing or out of range). `unknown` means the codebook's own unknown code. `unexpected` means a code outside the transcribed list. None of these tokens is imputed from other rows.

| Feature | Source | Type | Transformation | Missing or unknown | Why it can be known | Limitation |
| --- | --- | --- | --- | --- | --- | --- |
| `longitude` | `longitude` | numeric | Keep the source text if it parses as a number | Blank. Not imputed | Recorded location of the collision | 53 audited rows have no coordinate. Not an exposure |
| `latitude` | `latitude` | numeric | Same as longitude | Blank. Not imputed | Recorded location | Easting and northing are not also approved |
| `hour` | `time` | numeric | Hour from `HH:MM` | Blank if time is invalid | Collision time | The minute and the raw clock are not inputs |
| `weekday` | `day_of_week` | categorical | Codes 1 Sunday through 7 Saturday. If the code is absent, derive it from a valid date | `missing` if neither source works | Collision date | A valid `day_of_week` is kept even if it disagrees with the date |
| `month` | `date` | numeric | Month from `DD/MM/YYYY` | Blank if the date is invalid | Collision date | The year is not a model input |
| `season` | `date` | categorical | Winter Dec–Feb, spring Mar–May, summer Jun–Aug, autumn Sep–Nov | Blank if the date is invalid | Function of the collision date | Not a weather observation |
| `first_road_class` | `first_road_class` | categorical | Keep a codebook code | `missing` for `-1` | Road class at the reported site | The road number is not approved |
| `road_type` | `road_type` | categorical | Keep a codebook code | `missing` for `-1`, `unknown` for code 9 | Road layout | Code 12 stays 12 |
| `speed_limit` | `speed_limit` | categorical | Keep 20, 30, 40, 50, 60, or 70 | `missing` for `-1`, `unknown` for 99 | Posted limit | Not mean-imputed. The extract has no code 99 |
| `junction_detail` | `junction_detail` | categorical | 2024 code list only | `missing` for `-1`, `unknown` for 99 | Junction type at the site | Earlier years were converted by DfT. The historic column is excluded |
| `junction_control` | `junction_control` | categorical | Keep a codebook code | `missing` for `-1`, `unknown` for 9 | How the junction is controlled | Code 0 means not at a junction |
| `second_road_class` | `second_road_class` | categorical | Keep a codebook code | `missing` for `-1`, `unknown` for 9 | Second road at a junction | Code 0 means not at a junction. The road number is not approved |
| `pedestrian_crossing` | `pedestrian_crossing` | categorical | 2024 code list only | `missing` for `-1`, `unknown` for 99 | Crossing facility at the site | Historic crossing columns are excluded |
| `light_conditions` | `light_conditions` | categorical | Keep a codebook code, including 7 | `missing` for `-1` | Light at the collision time | Code 7 is darkness with lighting unknown, not a blank |
| `weather_conditions` | `weather_conditions` | categorical | Keep a codebook code | `missing` for `-1`, `unknown` for 9 | Reported weather | A reported category, not a station measurement |
| `road_surface_conditions` | `road_surface_conditions` | categorical | Keep a codebook code | `missing` for `-1`, `unknown` for 9 | Surface state at the site | Not a substitute for weather |
| `special_conditions_at_site` | `special_conditions_at_site` | categorical | Keep a codebook code | `missing` for `-1`, `unknown` for 9 | Site conditions such as roadworks | Many audited rows are `-1`. They stay `missing` |
| `urban_or_rural_area` | `urban_or_rural_area` | categorical | Keep 1 Urban, 2 Rural, or 3 Unallocated | `missing` for `-1` | Class of the recorded location | Unallocated stays code 3 |
| `trunk_road_flag` | `trunk_road_flag` | categorical | Keep 1 or 2 | `missing` for `-1` | Trunk status of the road | Code 1 is still labelled Highways England in the guide |

The raw `date`, raw `time`, and `collision_year` are not model inputs. `collision_index` is stored on the feature table so rows can be reconciled. It is not a predictor.

## Conditional fields

These are not approved and are not written as model inputs.

| Field | Why it is not approved |
| --- | --- |
| `location_easting_osgr`, `location_northing_osgr` | Same location as latitude and longitude. Using both systems is unresolved |
| `carriageway_hazards` | The 2024 list mixes site defects with "Involvement with previous collision". That mix is unresolved |
| `police_force` | Administrative reporter. It may proxy injury-based reporting. That use is not approved |
| `local_authority_ons_district` | Administrative area code with high cardinality |
| `local_authority_highway` | Administrative authority. Not approved as a road attribute |
| `first_road_number`, `second_road_number` | High-cardinality road identities. Class is the approved field |

## Excluded fields

| Field | Reason |
| --- | --- |
| `collision_severity` | Target. The mapped column `severity_serious_or_fatal` is also a label, not a predictor |
| `enhanced_severity_collision`, `collision_injury_based` | Target-derived. The enhanced scale is not interchangeable with the recorded label |
| `collision_adjusted_severity_serious`, `collision_adjusted_severity_slight` | Adjustment weights. Not applied and not predictors |
| `number_of_vehicles`, `number_of_casualties` | Counts produced by the collision |
| `did_police_officer_attend_scene_of_accident` | Post-event attendance |
| `collision_index`, `collision_ref_no` | Identifiers |
| `collision_year` | Split key |
| `date`, `time` | Replaced by month, season, weekday, and hour so the holdout year is not a feature |
| `local_authority_district` | Code `-1` means deprecated on 513,607 audited rows |
| `local_authority_highway_current` | The guide says this field arrived with the 2024 data and maps every collision onto the latest ONS list |
| `junction_detail_historic` | 2011 schema. It overlaps `junction_detail` |
| `pedestrian_crossing_human_control_historic`, `pedestrian_crossing_physical_facilities_historic` | Superseded by `pedestrian_crossing` |
| `carriageway_hazards_historic` | Superseded schema. The current hazards field is still only conditional |
| `lsoa_of_accident_location` | Small-area identifier, and it covers England and Wales only |

## Temporal policy

Assignment uses `collision_year` only. The ranges do not overlap. A random split is not used.

| Split | Years |
| --- | --- |
| Training | 2021, 2022, 2023 |
| Validation | 2024 |
| Test | 2025 |

## Open questions

- Whether British National Grid coordinates should replace latitude and longitude.
- Whether any `carriageway_hazards` code is only a site condition and could be approved on its own.
- Whether police force or ONS district should be used as a reporting-system or area control.
- The recorded serious and slight classes still mix injury-based and severity reporting. The feature table does not correct that.
- No historical crash counts are built. A count at time *t* would have to ignore events at *t* and later, and that feature is not in this specification.

The dashboard does not load this table. It does not show predictions, risk levels, or maps.
