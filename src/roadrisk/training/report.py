"""Render the validation comparison."""

from __future__ import annotations

from collections.abc import Mapping


def render_comparison(summary: Mapping[str, object]) -> str:
    """Write the validation note. Counts and scores come only from ``summary``."""

    decision = _mapping(summary["provisional_model"])
    provenance = _mapping(summary["provenance"])
    models = summary["models"]
    lines = [
        "# Baseline comparison",
        "",
        summary["question"],
        "",
        "These figures are 2024 validation scores for severity given a reported collision.",
        "They are not final test performance, and they do not estimate whether a collision occurs.",
        "",
        f"Provisional model: `{decision.get('model')}`.",
        "",
        str(decision.get("rule", "")),
        "",
        f"2025 rows held out and not scored: {provenance.get('test_rows_held_out')}.",
        "",
        "## Validation metrics",
        "",
        "| Model | Precision | Recall | F1 | Average precision | ROC-AUC | Brier |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    if isinstance(models, list):
        for row in models:
            if not isinstance(row, Mapping):
                continue
            metrics = _mapping(row["metrics"])
            lines.append(
                "| "
                f"{row.get('model')} | {_num(metrics.get('precision'))} | "
                f"{_num(metrics.get('recall'))} | {_num(metrics.get('f1'))} | "
                f"{_metric(metrics, 'average_precision')} | {_metric(metrics, 'roc_auc')} | "
                f"{_metric(metrics, 'brier')} |"
            )
    lines.extend(
        [
            "",
            "Precision, recall, and F1 use the positive class at the default 0.5 threshold.",
            "That threshold was not tuned.",
            "",
            "## Confusion matrices",
            "",
            "Each matrix is true rows by predicted columns, for classes 0 then 1.",
            "",
        ]
    )
    if isinstance(models, list):
        for row in models:
            if not isinstance(row, Mapping):
                continue
            matrix = _mapping(_mapping(row["metrics"]).get("confusion_matrix", {}))
            lines.append(f"- `{row.get('model')}`: {matrix.get('matrix')}")
    lines.extend(["", "## Provenance", ""])
    for key in (
        "feature_spec_version",
        "source_sha256",
        "training_rows",
        "training_years",
        "validation_rows",
        "validation_years",
        "random_seed",
    ):
        lines.append(f"- {key}: {provenance.get(key)}")
    lines.append("")
    return "\n".join(lines)


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}


def _metric(metrics: Mapping[str, object], name: str) -> str:
    status = metrics.get(f"{name}_status")
    if status != "defined":
        return "undefined"
    return _num(metrics.get(name))


def _num(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)
