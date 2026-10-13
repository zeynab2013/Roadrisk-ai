# Risk bands and explanations

Status: derived on 10 October 2026 from the frozen Phase 6 pipeline and the 2024 validation scores. The 2025 test evaluation was not used and was not rewritten.

The question stays the one in [data strategy](data-strategy.md). Given a reported personal-injury collision, the model estimates the probability that it was fatal or serious rather than slight. A band is a slice of that probability. It is a research label for the model output. It is not a grade of how safe a road is, and it is not the probability that a collision will occur.

There is no traffic-exposure denominator at the spatial and temporal grain of a collision. These pages do not invent traffic volumes, population, or exposure-adjusted rates.

## Frozen inputs

| Item | Value |
| --- | --- |
| Model | Histogram gradient boosting, sigmoid calibration |
| Binary classification threshold | 0.15 |
| Decision SHA-256 | `9461dce554913b7617c1632d5bd8a23ab3e4185542c3f5e65baab5fac14ef09b` |
| Selected pipeline SHA-256 | `43143b15178c5dc2dbe5c79ed6e12e1217d5ba6cefab737f5f7ac24f508bb478` |
| Feature specification | Version 1, 19 approved fields |
| Source SHA-256 | `06a03c0e5504175e23ed98e3e0b4767ac61d396c073405a1bddab9339c18f948` |
| Band file | `data/models/phase7-v1/risk-bands.json` |
| Created | 2026-10-10T17:16:30+00:00 |

The binary threshold comes from Phase 6. A probability at or above 0.15 is the fatal-or-serious class. That rule is unchanged. The two band boundaries below are a separate display of where a score sits in the 2024 score distribution.

The feature table is one file, so the band command loads 2025 rows and then keeps only the 2024 validation split. Those 2025 rows are not scored. The command does not call the held-out loader and does not write `test-evaluation.json`.

## How the boundaries were chosen

The objective was fixed in code before the 2024 scores were summarized. On the frozen model's 2024 validation probabilities only:

- the lower boundary is the 0.50 quantile
- the upper boundary is the 0.90 quantile

NumPy's linear quantile method is used. The cuts describe the distribution of model output. They were not chosen to maximize a safety metric, and they were not fit to labels. Phase 6 did not set a cost ratio, so these cuts do not inherit one. Fixed cuts such as 0.33 and 0.66 are not used.

The trade-off is deliberate. Sigmoid scores on this model sit in a narrow band: the 2024 mean score is 0.2063, and Phase 6 reliability bins above 0.7 were empty. Equal-width probability cuts would leave the top band empty. Quantiles keep a lower half, a middle portion, and a top tenth of recorded validation collisions. The top tenth is a minority of the table. A higher quantile would make `HIGH` too thin to read; a lower one would make it most of the table.

On 100,927 validation rows the command stored:

| Boundary | Role | Value |
| --- | --- | --- |
| `low_below` | 0.50 quantile | 0.196970155937929 |
| `high_at_or_above` | 0.90 quantile | 0.3126165522731136 |

Assignment is deterministic:

- `LOW` when the probability is strictly below 0.196970155937929
- `MEDIUM` when it is at or above that value and strictly below 0.3126165522731136
- `HIGH` when it is at or above 0.3126165522731136

The lower boundary belongs to `MEDIUM`. The upper boundary belongs to `HIGH`. Both cuts are finite and satisfy `0 < lower < upper < 1`. The saved file records `test_period_used: false`, the validation year 2024, the row count 100,927, the decision hash, and the pipeline hash. A loader rejects a missing file, unordered cuts, a file that says the test period was used, or a hash that does not match the frozen decision.

Because 0.15 is below the median score, a row can be the fatal-or-serious class and still be `LOW`. The class answers the Phase 6 operating point. The band answers where the score sits among 2024 scores. `LOW` does not mean the model called the collision slight.

Across the same 100,927 rows the three bands contain 50,463 `LOW`, 40,371 `MEDIUM`, and 10,093 `HIGH` collisions. That is the lower half, the next portion, and the top tenth, with boundary ties assigned as above.

## What a band means

`LOW`, `MEDIUM`, and `HIGH` are names for those three slices. They are useful for exploratory comparison of model output. They are not an official safety standard, and a higher band is not evidence that a place is dangerous. The same limitation applies to every screen that later shows these names: the text should say they are model-output bands for a reported collision.

## Explanations

`explain_frame` scores the frozen calibrated pipeline. It needs the 19 approved columns and the Phase 6 threshold, which the caller must pass. The default is not 0.5. A row whose year is 2025, or whose split is `test`, is rejected before scoring.

For each approved field, the function replaces that field with the missing value the fitted pipeline already imputes, scores the row again, and records the change in probability. The observed value is stored separately from that change. The change is a local sensitivity: how this fitted model responds when one recorded field becomes missing. It does not show that the field caused the collision or the injury. It is not a global ranking, and a global ranking is not a reason for that row.

Missing and unknown values follow the feature transform. Blank numeric inputs become missing and are imputed inside the pipeline. Categorical blanks and the unknown token stay the values the pipeline was trained to accept. Target fields and excluded columns are not explanation features.

If a probability is missing or outside `[0, 1]`, the function raises. It does not invent a sentence in place of a failed score.

### Global importance is a different summary

`global_permutation_summary` measures the drop in average precision when each approved column is shuffled. The run used a stratified sample of 2,000 rows from the 2024 validation split, three repeats, seed 42, and one job. The 2024 label is the scoring target for that drop. It is not an explanation of one collision, and it was not used to choose the band boundaries or the binary threshold.

On this sample the largest mean drop was latitude, about 0.041 average precision. Several fields have a negative mean drop. On a 2,000-row sample that is variation in the estimate, not evidence that the field prevents serious injury. The full table is `data/models/phase7-v1/global-importance.json`. SHAP is not installed and was not added.

## Area summaries

The grouping field is `urban_or_rural_area`. It is an approved feature with a closed code list: `1` Urban, `2` Rural, `3` Unallocated. The summary uses the human-readable labels for those three codes only.

Other geographic fields were not used:

- `local_authority_district` is deprecated (`-1`) on 513,607 of 513,801 audited rows, and it is not an approved feature.
- `local_authority_ons_district` and `local_authority_highway` are conditional codes. The feature build does not emit them.
- LSOA is not an approved feature.

The summary reports the area id, label, number of recorded collisions, the count and share in each band, and the mean calibrated probability. Rows with a blank or missing code are counted as missing and left out of the groups. Any other code is counted as unsupported and left out. A group with fewer than the support minimum is omitted from `supported_groups`. The default minimum is 50. That list is ordered by the share of `HIGH` model output, then by area id. The order is a sort of those shares. It is not a ranking of safe or unsafe places.

`urban_or_rural_area` is also a model input. A difference between urban and rural scores partly reflects that input, together with the other recorded circumstances of the collisions that were reported. It is not an exposure-adjusted rate and it is not proof that one setting is more dangerous.

2024 validation result, support minimum 50:

| Area | Collisions | LOW | MEDIUM | HIGH | Mean probability |
| --- | ---: | ---: | ---: | ---: | ---: |
| Urban (`1`) | 67,304 | 39,543 | 24,500 | 3,261 | 0.1875 |
| Rural (`2`) | 33,620 | 10,920 | 15,868 | 6,832 | 0.2439 |
| Unallocated (`3`) | 3 | 0 | 3 | 0 | 0.2562 |

Missing-location rows: 0. Unsupported codes: 0. The three groups sum to 100,927. Unallocated is below the support minimum, so it is absent from `supported_groups`. Rural has a higher share of `HIGH` scores among recorded collisions (0.2032) than urban (0.0485). That share is the quantity in the table. It does not measure how many collisions occur per vehicle or per resident, and reporting practice can differ between urban and rural roads.

Small counts move a share a lot. Three unallocated rows are all `MEDIUM` in this split. That is a description of three records, not a property of unallocated roads in general. The same caution applies to any later group with a count near the support minimum.

## Reproduce

From the project root, with `.venv312`, the verified collision file, and the frozen Phase 6 artifacts:

```powershell
.\.venv312\Scripts\python.exe -m roadrisk.inference bands --manifest configs/data_manifest.json
```

The command writes `data/models/phase7-v1/risk-bands.json`, `group-summary.json`, and `global-importance.json`, and copies them to `reports/phase7/`. Those directories are gitignored. A second run rewrites the Phase 7 files, including `created_at`. It does not rewrite `data/models/phase6-v1/` or `data/models/baselines-v1/`. Do not run `python -m roadrisk.training select` or `python -m roadrisk.training evaluate` as part of this phase. `evaluate` is the Phase 6 command that scores 2025, and a valid saved result is refused.

To explain a caller-supplied CSV of approved feature columns:

```powershell
.\.venv312\Scripts\python.exe -m roadrisk.inference explain --rows path\to\rows.csv --bands data\models\phase7-v1\risk-bands.json --output reports\phase7\explanations.json
```

The rows file must not be the 2025 test split. If `collision_year` is 2025 or `split` is `test`, the command stops before scoring. The output path must sit outside the Phase 5 and Phase 6 artifact directories.

Library entry points, which a later API should call, are `load_frozen_model`, `explain_frame`, `assign_category`, `load_risk_bands`, and `summarize_groups`.
