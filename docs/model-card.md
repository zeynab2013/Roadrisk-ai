# Model card

Status: documentation of the frozen local artifacts. The Python package version in `pyproject.toml` is `0.1.0`. No GitHub release has been created. This card does not change the model.

The numbers in the 2025 table are copied from [`data/models/phase6-v1/test-evaluation.json`](../data/models/phase6-v1/test-evaluation.json). They were not recomputed for this card. A rounded summary of the same file is in [phase 6](phase6.md).

## Identity

| Item | Record |
| --- | --- |
| Package | `roadrisk` `0.1.0` |
| Model | `hist_gradient_boosting` |
| API artifact role | `frozen_phase6` |
| Decision SHA-256 | `9461dce554913b7617c1632d5bd8a23ab3e4185542c3f5e65baab5fac14ef09b` |
| Pipeline SHA-256 | `43143b15178c5dc2dbe5c79ed6e12e1217d5ba6cefab737f5f7ac24f508bb478` |
| Feature specification | Version 1, 19 approved fields |
| Calibration | Sigmoid, fit on 2021–2023 out-of-fold predictions |
| Classification threshold | `0.15` |
| Held-out evaluation | `2026-10-10T16:30:04+00:00` |

`GET /model` reports `model_version` as that decision SHA-256. The response fields are defined in `apps/api/schemas.py`. A recorded response on 13 October 2026 returned `hist_gradient_boosting`, `frozen_phase6`, sigmoid calibration, threshold `0.15`, and the band cuts below.

## Purpose

Given a reported personal-injury collision, the model estimates whether it was fatal or serious rather than slight.

That is the question stored in the frozen decision and in `test-evaluation.json`. The positive class is official severity codes `1` and `2`, encoded as `1`. The negative class is code `3` (slight), encoded as `0`.

This is not the probability that a collision occurs. The artifact field `not_estimated` is `Whether a collision occurs.` The available files do not contain traffic exposure at the place and time of one collision. See [data strategy](data-strategy.md).

## Intended use

The intended users recorded in the data strategy are analysts and reviewers studying the circumstances of police-reported personal-injury collisions. A score can be compared with the recorded 2025 metrics and with the research bands below. The HTTP service and dashboard display that score. They do not create a new model.

## Unsupported interpretations

- A score is not the probability that a collision will happen at a place or time.
- `LOW`, `MEDIUM`, and `HIGH` are not official safety ratings and are not a statement that a road is safe or unsafe.
- The bands are not exposure-adjusted collision rates.
- A single prediction is not a guarantee for a person, a journey, or a site.
- Threshold `0.15` is not a measured cost ratio and is not a clinical or operational optimum. The frozen decision says false positives and false negatives are both reported.
- Beating a historical dummy ranking on this extract does not show that the model is reliable for road-safety decisions. That limitation is stored in `test-evaluation.json`.

## Data split

Confirmed in [`frozen-config.json`](../data/models/phase6-v1/frozen-config.json) and [features](features.md):

| Split | Years | Role |
| --- | --- | --- |
| Training | 2021, 2022, 2023 | Fit the Phase 5 candidate and the sigmoid calibrator |
| Validation | 2024 | Choose the calibration method and the threshold. These scores are selection results, not an unbiased future estimate |
| Test | 2025 | Held out. `test_used_for_selection` is `false` in the evaluation file |

The feature build recorded 311,349 training rows, 100,927 validation rows, and 101,525 test rows. The 2025 evaluation file also records 101,525 rows. Feature construction is in [features](features.md). Baseline comparison is in [baselines](baselines.md).

## Classification and research bands

The fatal-or-serious class is probability at or above `0.15`. Ranking metrics in the evaluation file do not use that cutoff. The file says so in `threshold_note`: `Caller-supplied threshold. Ranking metrics do not use it.`

The research bands are a separate display. They come from [`data/models/phase7-v1/risk-bands.json`](../data/models/phase7-v1/risk-bands.json), created `2026-10-10T17:16:30+00:00` from the frozen model's 2024 validation scores only. `test_period_used` is `false`. The cuts are the 0.50 and 0.90 quantiles of those scores, not a safety standard.

| Band | Rule |
| --- | --- |
| `LOW` | probability `<` `0.196970155937929` |
| `MEDIUM` | `0.196970155937929` `<=` probability `<` `0.3126165522731136` |
| `HIGH` | probability `>=` `0.3126165522731136` |

Because `0.15` is below `0.196970155937929`, a row can be classed fatal or serious and still be `LOW`. `LOW` does not mean the model called the collision slight. The policy is in [risk policy](risk-policy.md).

## 2025 metrics

Scored once. The evaluation timestamp is `2026-10-10T16:30:04+00:00`. Positive label `1` means fatal or serious.

| Metric | Value in `test-evaluation.json` |
| --- | --- |
| Rows | `101525` |
| Positive rows | `26644` |
| Predicted positive | `77627` |
| Precision | `0.2874644131552166` |
| Recall | `0.8375243957363759` |
| F1 | `0.4280192958732533` |
| Accuracy | `0.4125486333415415` |
| Average precision | `0.35679507352024975` |
| ROC-AUC | `0.6078228667181302` |
| Brier score | `0.19020457244778005` |
| Log loss | `0.5691451034690374` |
| Threshold used for the class counts | `0.15` |

Average precision, ROC-AUC, Brier score, and log loss are marked `defined` in the file. The presence of a metric is not evidence that the model is effective. Precision `0.2874644131552166` means that, at this threshold, most predicted-positive rows were not recorded as fatal or serious. Recall `0.8375243957363759` means most recorded fatal-or-serious rows were predicted positive. The stored limitation says discrimination on this task is modest and the classes are uneven.

### Confusion matrix

`labels` are `[0, 1]`. The file's `order` is `rows are true 0 then 1; columns are predicted 0 then 1`. Label `0` is slight. Label `1` is fatal or serious.

|  | Predicted 0 (slight) | Predicted 1 (fatal or serious) |
| --- | --- | --- |
| True 0 (slight) | `19569` | `55312` |
| True 1 (fatal or serious) | `4329` | `22315` |

`19569` is true slight predicted slight. `55312` is true slight predicted fatal or serious. `4329` is true fatal or serious predicted slight. `22315` is true fatal or serious predicted fatal or serious. These four counts are the matrix in the artifact. [phase 6](phase6.md) prints the same matrix and rounds the other metrics to four decimal places. Those rounded figures are not repeated here.

## The frozen-config snapshot is older than the score

[`frozen-config.json`](../data/models/phase6-v1/frozen-config.json) was written at `2026-10-10T16:28:53+00:00`. It still contains `test_year_scored: false` and the note `2025 has not been scored.` That describes the snapshot at creation time, before the held-out score.

The completed score is `test-evaluation.json` at `2026-10-10T16:30:04+00:00`. Both files name the same decision SHA-256. This card uses the evaluation file for every 2025 metric. It does not treat `test_year_scored: false` as a statement that the test year is still unscored.

## Limitations

These limits are part of the recorded artifacts and the existing technical notes. They are not a claim that a later release has removed them.

- **Scope.** The rows are police-reported personal-injury collisions in the STATS19 extract for 2021–2025. Damage-only collisions are outside the file. Journeys with no recorded injury collision are not in the training table.
- **Time.** The threshold and calibration method were chosen on 2024. The 2025 numbers are one later year, not a standing forecast. Reporting practice and the mix of slight and serious collisions can change. The evaluation file states that shift as a limitation.
- **Geography.** Coordinates and `urban_or_rural_area` are approved inputs. Administrative areas were not used as model groups. A band is not a ranking of places. There is no exposure denominator. See [risk policy](risk-policy.md) and [data strategy](data-strategy.md).
- **Threshold.** Of the `101525` test rows, `77627` were predicted positive at `0.15`. The operating point was chosen to raise 2024 positive-class F1, not because a cost of a miss or a false alarm was measured.
- **Calibration.** Sigmoid was selected because it lowered 2024 Brier score and log loss while keeping average precision within the written rule. Those 2024 figures are selection results. Phase 6 records remaining under-confidence in the 2024 reliability bins and empty bins above 0.7. The 2025 Brier score above is the held-out probability score, not a second calibration.
- **Explanations.** Replacing one recorded field with missing shows how this fitted model responds. It does not show that the field caused the collision or the injury. A global importance ranking is a different summary. SHAP is not used.
- **What was not done.** No hyperparameter search was run. The evaluation does not measure whether a score would improve a road-safety decision.
- **Reproducibility of the lock.** A later `evaluate` refuses a result that matches this decision. Deleting the local evaluation files removes that lock. The guard is not tamper-proof. The model files are gitignored. A clean checkout does not contain them until they are supplied separately.

## Where the record lives

- [Phase 6 evaluation](phase6.md)
- [Risk bands and explanations](risk-policy.md)
- [Data strategy](data-strategy.md)
- [Feature specification](features.md)
- [Baselines](baselines.md)
- [Prediction API](api.md)
- [`data/models/phase6-v1/test-evaluation.json`](../data/models/phase6-v1/test-evaluation.json)
- [`data/models/phase6-v1/frozen-config.json`](../data/models/phase6-v1/frozen-config.json)
- [`data/models/phase6-v1/selected-pipeline.joblib`](../data/models/phase6-v1/selected-pipeline.joblib)
- [`data/models/phase7-v1/risk-bands.json`](../data/models/phase7-v1/risk-bands.json)
