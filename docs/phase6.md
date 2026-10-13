# Phase 6 evaluation

Status: selected on 10 October 2026 and scored once the same day. The question is whether a reported personal-injury collision was fatal or serious. These figures do not estimate whether a collision occurs, and they do not show that the model is ready for road-safety decisions.

The historical Phase 5 table is unchanged in [baselines](baselines.md). This note has three separate parts: that historical result, the 2024 selection, and the single 2025 score.

## A. Historical Phase 5 result

Phase 5 fit four untuned models on 2021–2023 and compared them on 2024 at threshold 0.5. The rule ranked positive-class average precision. Scores within 0.005 were broken by the lower Brier score. Random forest led on average precision at 0.3474. Histogram gradient boosting was 0.3430, inside that band, with Brier score 0.2202 against the forest's 0.2302. The dummy classifier's Brier score was 0.1869, better than every balanced model. Those numbers are validation results from Phase 5. They were not recomputed here. The artifact directory `data/models/baselines-v1/` was not overwritten.

## B. Validation and selection

2024 was used to choose the calibration method and the threshold. Those 2024 scores are model-selection results, not an unbiased estimate of future performance. The feature table is one file, so loading it also reads the 2025 rows. Those labels were not used to select the model, the calibration method, or the threshold.

### Calibration

The uncalibrated candidate is the Phase 5 histogram gradient boosting artifact. Sigmoid and isotonic calibrators were new fits of the same settings. Each used `CalibratedClassifierCV` with three shuffled stratified folds, `ensemble=False`, and seed 42, so the calibrator was fit on out-of-fold training predictions. They were not fit on 2024 or 2025.

A calibrator was kept only when 2024 Brier score and log loss both improved and average precision fell by at most 0.01. If both qualified and their Brier scores were within 0.001, sigmoid was preferred.

| Method | Average precision | ROC-AUC | Brier | Log loss | ECE |
| --- | --- | --- | --- | --- | --- |
| Uncalibrated | 0.3430 | 0.6169 | 0.2202 | 0.6298 | 0.1960 |
| Sigmoid | 0.3430 | 0.6169 | 0.1820 | 0.5483 | 0.0421 |
| Isotonic | 0.3398 | 0.6168 | 0.1820 | 0.5483 | 0.0422 |

Sigmoid won. It matched the uncalibrated ranking and lowered both probability scores. Isotonic was inside the average-precision limit but its Brier score was slightly worse, and the two Brier scores were inside the 0.001 band, so the rule kept sigmoid. Full values and ten reliability bins are in `calibration-comparison.json`.

Sigmoid pulls the balanced-model scores down toward the observed rate. At threshold 0.5 it predicted only 301 of 100,927 validation collisions as fatal or serious (precision 0.6146, recall 0.0074, F1 0.0146). The populated reliability bins are still a little low: observed rates sit about three to four points above the mean predicted probability. Bins above 0.7 were empty. Expected calibration error fell from 0.1960 to 0.0421. The Phase 5 dummy Brier score on this same 2024 split was 0.1869. Sigmoid's 0.1820 is lower than that historical dummy score. The dummy was not refit or rescored for this phase.

### Threshold

The objective was fixed before the sweep. Maximize positive-class F1 on the 2024 scores of the chosen probability model. Keep 0.5 unless F1 improves by at least 0.01. The grid is 0.05 through 0.95 in steps of 0.05. This is not a safety, clinical, or operational optimum, and it is not a cost ratio.

| Threshold | Precision | Recall | F1 | Predicted positive | False positives | False negatives |
| --- | --- | --- | --- | --- | --- | --- |
| 0.05 | 0.2530 | 0.9971 | 0.4036 | 98,786 | 73,789 | 72 |
| 0.10 | 0.2596 | 0.9759 | 0.4101 | 94,246 | 69,782 | 605 |
| 0.15 | 0.2771 | 0.8572 | 0.4188 | 77,552 | 56,062 | 3,579 |
| 0.20 | 0.3112 | 0.6046 | 0.4109 | 48,699 | 33,543 | 9,913 |
| 0.50 | 0.6146 | 0.0074 | 0.0146 | 301 | 116 | 24,884 |

Threshold 0.15 had the highest F1, 0.4188, against 0.0146 at 0.5. The margin is far above 0.01, so 0.5 was not retained. The confusion matrix at 0.15 is `[[19796, 56062], [3579, 21490]]`: 56,062 slight collisions are called fatal or serious, and 3,579 fatal or serious collisions are missed. About 77% of validation rows are predicted positive. Accuracy at this point is 0.4091 and was not used to choose it. Average precision stays 0.3430 and ROC-AUC stays 0.6169 at every threshold, because those metrics do not use the cutoff. Brier score 0.1820 and log loss 0.5483 likewise use the probabilities.

The frozen decision SHA-256 is `9461dce554913b7617c1632d5bd8a23ab3e4185542c3f5e65baab5fac14ef09b`. Feature specification version 1. Source SHA-256 `06a03c0e5504175e23ed98e3e0b4767ac61d396c073405a1bddab9339c18f948`. The selected pipeline SHA-256 is `43143b15178c5dc2dbe5c79ed6e12e1217d5ba6cefab737f5f7ac24f508bb478`.

`frozen-config.json` is the pre-test decision snapshot. It was written before 2025 was scored, so its `test_year_scored` field is false. That describes the file when it was created. It does not mean the project has no test result. The completed score is `test-evaluation.json`.

## C. Final 2025 test

The frozen pipeline was scored once on 10 October 2026 at 16:30:04 UTC. 2025 labels were not used to choose the model, the calibration method, or the threshold. A later `evaluate` reads the saved result before it loads the feature table. A result that matches the frozen decision is refused. An unreadable or inconsistent result is an invalid lock and is not replaced or rescored.

| Item | Value |
| --- | --- |
| Rows | 101,525 |
| Positive rows (fatal or serious) | 26,644 |
| Predicted positive | 77,627 |
| Precision | 0.2875 |
| Recall | 0.8375 |
| F1 | 0.4280 |
| Accuracy | 0.4125 |
| Average precision | 0.3568 |
| ROC-AUC | 0.6078 |
| Brier | 0.1902 |
| Log loss | 0.5691 |
| Confusion matrix | `[[19569, 55312], [4329, 22315]]` |

The matrix counts 19,569 true negatives, 55,312 false positives, 4,329 false negatives, and 22,315 true positives. They sum to 101,525.

Average precision on 2025 is 0.3568, a little above the 2024 selection value of 0.3430. ROC-AUC is 0.6078, a little below the 2024 value of 0.6169. The Phase 5 2024 dummy average precision was 0.2484 and its ROC-AUC was 0.5. The dummy was not scored on 2025, so there is no 2025 dummy confusion matrix. Beating that historical dummy on ranking does not make the model reliable for deployment.

## Limits

Discrimination remains modest. The positive class is about a quarter of reported injury collisions, and the chosen threshold flags most rows. Sigmoid calibration improved probability scores on 2024 and left a small under-confidence in the reliability bins. Reporting practice and the mix of slight and serious collisions can shift between years. No hyperparameter search was run. Nothing here measures whether the score would change a road-safety decision for the better.

Phase 7 later read this frozen pipeline and the 2024 validation scores to set research bands and explanations. That work did not change the numbers in this file, the frozen decision, or `test-evaluation.json`.

## Reproduce

From the project root, with `.venv312` and the verified collision file:

```powershell
.\.venv312\Scripts\python.exe -m roadrisk.training select --manifest configs/data_manifest.json
.\.venv312\Scripts\python.exe -m roadrisk.training evaluate --manifest configs/data_manifest.json
```

`select` writes `data/models/phase6-v1/` and copies the selection files to `reports/phase6/`. Run it before `evaluate`. `evaluate` appends `test-evaluation.json`. A later run checks that file before loading the feature table. A matching result is refused. A broken result is an invalid lock and is not rewritten. Re-running `select` after a valid test result is also refused. Deleting or replacing `test-evaluation.json` and `frozen-config.json` removes this local record. The guard is not tamper-proof, and it does not make another score impossible. Both directories are gitignored. The Phase 5 command remains `python -m roadrisk.training train` and writes only `data/models/baselines-v1/`.
