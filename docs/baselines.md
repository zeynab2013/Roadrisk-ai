# Baseline comparison

Status: trained on 9 October 2026. The question is whether a reported personal-injury collision was fatal or serious. These numbers are 2024 validation scores. They are not 2025 test performance, and they do not estimate whether a collision occurs.

The positive class is recorded severity code 1 or 2, stored as `severity_serious_or_fatal` = 1. Slight, code 3, is 0. The 19 approved features from specification version 1 are the only inputs. No conditional field was added. `collision_index` is not a predictor.

## Command

From the Python 3.12 environment:

```powershell
python -m roadrisk.training train --manifest configs/data_manifest.json
```

The command checks the raw collision SHA-256 before fitting. It reads `data/processed/collision-features-v1.csv` and refuses a feature table whose provenance does not match that digest and specification version 1.

Artifacts, all gitignored:

- `data/models/baselines-v1/*.joblib` — each file is the preprocessing pipeline and the estimator together
- `data/models/baselines-v1/comparison.json`
- `data/models/baselines-v1/comparison.md`
- Copies of the comparison files in `reports/training/`

## Data used

| Split | Years | Rows | Role in this phase |
| --- | --- | --- | --- |
| Training | 2021–2023 | 311,349 | Fit imputers, encoders, and estimators |
| Validation | 2024 | 100,927 | Compare the four models |
| Test | 2025 | 101,525 | Counted and held out. Not scored |

Source SHA-256: `06a03c0e5504175e23ed98e3e0b4767ac61d396c073405a1bddab9339c18f948`.

`comparison.json` records `test_year_scored: false`.

## Preprocessing

Fitted inside each pipeline on training rows only.

- Numeric columns (`longitude`, `latitude`, `hour`, `month`) use a median imputer. Logistic regression then standardizes those columns. The other models do not scale them. One-hot columns are not scaled.
- Categorical columns use a constant fill of `missing`, then either one-hot encoding with unknown categories ignored, or, for gradient boosting, an ordinal encoding that leaves unknown categories missing.
- Histogram gradient boosting receives those ordinal columns as native categorical features.
- `class_weight="balanced"` is set on the logistic, forest, and boosting models so the default 0.5 threshold is not a majority-class rule. The dummy classifier uses the training class prior instead. These settings were fixed before the validation scores were read. There was no hyperparameter search.

Random seed 42. Forest `n_jobs=-1`. Boosting `early_stopping` is off, so it does not hold out part of the training period.

Environment: Python 3.12.10, scikit-learn 1.9.1, numpy 2.5.3, pandas 3.0.6, joblib 1.6.0. The Python 3.10 `.venv` was not changed. `requires-python` remains `>=3.10`.

## 2024 validation

Positive-class precision, recall, and F1 use threshold 0.5. That threshold was not tuned.

| Model | Precision | Recall | F1 | Average precision | ROC-AUC | Brier |
| --- | --- | --- | --- | --- | --- | --- |
| Dummy, prior | 0.0000 | 0.0000 | 0.0000 | 0.2484 | 0.5000 | 0.1869 |
| Logistic regression | 0.3143 | 0.4820 | 0.3805 | 0.3314 | 0.6019 | 0.2300 |
| Random forest | 0.3338 | 0.4569 | 0.3858 | 0.3474 | 0.6187 | 0.2302 |
| Histogram gradient boosting | 0.3396 | 0.4175 | 0.3745 | 0.3430 | 0.6169 | 0.2202 |

Confusion matrices, true rows by predicted columns, classes 0 then 1:

| Model | Matrix |
| --- | --- |
| Dummy | [[75858, 0], [25069, 0]] |
| Logistic regression | [[49495, 26363], [12986, 12083]] |
| Random forest | [[53002, 22856], [13616, 11453]] |
| Histogram gradient boosting | [[55507, 20351], [14603, 10466]] |

The dummy row predicts slight for every 2024 collision. Its average precision equals the 2024 positive share, and its ROC-AUC is 0.5. Its Brier score is the best of the four because the prior matches the class mix, while balanced class weights push the other models' probabilities away from that mix.

All three learned models beat the dummy on average precision. Separation is modest: ROC-AUC is about 0.60 to 0.62. At the untuned 0.5 threshold, precision stays near 0.31 to 0.34 while recall sits between about 0.42 and 0.48.

## Provisional choice

Histogram gradient boosting.

The rule, fixed before this run, ranks positive-class average precision on 2024. Models must beat the dummy. If the best scores fall within 0.005 average precision, the lower Brier score wins. Random forest leads on average precision at 0.3474. Gradient boosting is 0.3430, inside that band, and its Brier score is 0.2202 against the forest's 0.2302. Logistic regression is outside the band.

This is a provisional baseline, not a production model and not a public-safety validation. The 0.5 threshold is still the library default.

## What remains

Class weights helped recall and ranking, and they hurt Brier score relative to the dummy prior. This table is the historical Phase 5 result and was not replaced. In this Phase 5 record, 2025 has not been scored. Calibration, the later threshold, and the single 2025 score are in [phase 6](phase6.md). A training-period hyperparameter search was not run.
