"""Render an audit dictionary as JSON and Markdown."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path


def write_audit(report: Mapping[str, object], output_dir: Path) -> tuple[Path, Path]:
    """Write ``collision-audit.json`` and ``collision-audit.md``."""

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "collision-audit.json"
    markdown_path = output_dir / "collision-audit.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def render_markdown(report: Mapping[str, object]) -> str:
    """Return a readable audit. Counts come only from ``report``."""

    source = _mapping(report["source"])
    population = _mapping(report["population"])
    target = _mapping(report["target"])
    splits = _mapping(report["splits"])
    duplicates = _mapping(report["duplicates"])
    time = _mapping(report["time"])
    coordinates = _mapping(report["coordinates"])
    grid = _mapping(report["national_grid"])
    adjusted = _mapping(report["adjusted_fields"])
    lines = [
        "# Collision data-quality audit",
        "",
        f"Generated at: {report['generated_at']}",
        "",
        "## Source",
        "",
        f"- Dataset: {source.get('dataset_name', '')}",
        f"- File id: {source.get('manifest_file_id', '')}",
        f"- Filename: {source.get('filename', '')}",
        f"- SHA-256: `{source.get('sha256', '')}`",
        f"- Bytes: {source.get('byte_size', '')}",
        f"- Manifest schema version: {source.get('schema_version', '')}",
        "",
        "## Shape",
        "",
        f"- Rows: {report['row_count']}",
        f"- Columns: {report['column_count']}",
        "",
        "## Target",
        "",
        str(target.get("question", "")),
        "",
        f"Status: `{target.get('status', '')}`.",
        "",
        str(target.get("status_reason", "")),
        "",
        "| Code | Label | Class | Rows | Percent |",
        "| --- | --- | --- | --- | --- |",
    ]
    classes = target.get("classes", [])
    if isinstance(classes, list):
        for item in classes:
            if isinstance(item, dict):
                lines.append(
                    f"| {item['code']} | {item['label']} | {item['class']} | "
                    f"{item['rows']} | {item['percent']} |"
                )
    lines.extend(
        [
            "",
            f"Positive rows (fatal or serious): {target.get('positive_rows')} "
            f"({target.get('positive_percent')}%).",
            f"Slight rows: {target.get('negative_rows')} ({target.get('negative_percent')}%).",
            f"Invalid or missing severity values: `{target.get('invalid_or_missing')}`.",
            "",
            "This is severity given a reported collision, not the probability a collision occurs.",
            "",
            "## Modelling population",
            "",
        ]
    )
    rules = population.get("rules", [])
    if isinstance(rules, list):
        lines.extend(f"- {rule}" for rule in rules)
    lines.extend(
        [
            "",
            f"Retained: {population.get('retained_rows')} ({population.get('retained_percent')}%).",
            f"Excluded: {population.get('excluded_rows')} ({population.get('excluded_percent')}%).",
            f"Exclusion reasons: `{population.get('exclusion_reason_counts')}`.",
            "",
            "## Planned split",
            "",
            "Positive rows below are fatal or serious counts. They are not model scores.",
            "",
        ]
    )
    for key in ("training", "validation", "test"):
        block = _mapping(splits[key])
        lines.append(
            f"- {block.get('name')}: years {block.get('years')}, rows {block.get('rows')}, "
            f"positive rows {block.get('positive_rows')} ({block.get('positive_percent')}%)."
        )
    lines.extend(
        [
            "",
            f"Rows outside the planned years: `{splits.get('rows_outside_planned_years')}`.",
            "",
            "| Year | Rows | Fatal | Serious | Slight |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    by_year = splits.get("by_year", [])
    if isinstance(by_year, list):
        for item in by_year:
            if isinstance(item, dict):
                severity = item.get("severity", {})
                if isinstance(severity, dict):
                    lines.append(
                        f"| {item.get('year')} | {item.get('rows')} | {severity.get('1', 0)} | "
                        f"{severity.get('2', 0)} | {severity.get('3', 0)} |"
                    )
    lines.extend(
        [
            "",
            "## Identifiers and time",
            "",
            f"- Duplicate collision_index rows: {duplicates.get('duplicate_collision_index_rows')}",
            f"- Blank `collision_index` rows: {duplicates.get('blank_collision_index_rows')}",
            f"- Conflicting duplicate rows: {duplicates.get('conflicting_duplicate_rows')}",
            f"- Invalid dates: {time.get('invalid_dates')}",
            f"- Blank dates: {time.get('blank_dates')}",
            f"- Year/date mismatches: {time.get('year_date_mismatches')}",
            f"- Invalid times: {time.get('invalid_times')}",
            f"- Blank times: {time.get('blank_times')}",
            "",
            "## Coordinates",
            "",
            f"- Missing latitude or longitude: {coordinates.get('missing_latitude_or_longitude')}",
            f"- Non-numeric coordinates: {coordinates.get('non_numeric')}",
            f"- Origin points: {coordinates.get('origin_points')}",
            "- Outside the Great Britain window: "
            f"{coordinates.get('outside_great_britain_window')}",
            (
                f"- Longitude range: {coordinates.get('longitude_min')} "
                f"to {coordinates.get('longitude_max')}"
            ),
            (
                f"- Latitude range: {coordinates.get('latitude_min')} "
                f"to {coordinates.get('latitude_max')}"
            ),
            "",
            "Points outside the window are suspicious observations. They are not deleted.",
            "",
            "## National grid",
            "",
            str(grid.get("status", "")),
            "",
            f"- Missing easting or northing: {grid.get('missing_easting_or_northing', 'not run')}",
            f"- Non-numeric grid values: {grid.get('non_numeric', 'not run')}",
            f"- Both coordinates zero: {grid.get('both_zero', 'not run')}",
            f"- Outside the grid window: {grid.get('outside_great_britain_grid', 'n/a')}",
            "",
            "## Adjustment and enhanced severity",
            "",
            str(adjusted.get("reason", "")),
            "",
            f"- Blank weight rows: {adjusted.get('blank_rows')}",
            f"- Non-numeric weight rows: {adjusted.get('non_numeric_rows')}",
            f"- Both weights zero: {adjusted.get('both_zero_rows')}",
            f"- Weights sum to one: {adjusted.get('weights_sum_to_one_rows')}",
            f"- Other weight rows: {adjusted.get('other_rows')}",
            (
                f"- Serious weight range: {adjusted.get('serious_min')} "
                f"to {adjusted.get('serious_max')}"
            ),
            (
                f"- Slight weight range: {adjusted.get('slight_min')} "
                f"to {adjusted.get('slight_max')}"
            ),
            "",
            "| Recorded severity | Weight pattern | Rows |",
            "| --- | --- | --- |",
        ]
    )
    patterns = adjusted.get("pattern_by_recorded_severity", [])
    if isinstance(patterns, list):
        for item in patterns:
            if isinstance(item, dict):
                lines.append(
                    "| "
                    f"{item.get('collision_severity')} | {item.get('pattern')} | "
                    f"{item.get('rows')} |"
                )
    related = _mapping(report["related_severity_fields"])
    enhanced = _mapping(related["enhanced_severity_collision"])
    injury = _mapping(related["collision_injury_based"])
    lines.extend(
        [
            "",
            str(enhanced.get("reason", "")),
            "",
            str(injury.get("reason", "")),
            "",
            "## Findings",
            "",
        ]
    )
    findings = report.get("findings", [])
    if isinstance(findings, list):
        for item in findings:
            if isinstance(item, dict):
                lines.append(f"- `{item.get('level')}` `{item.get('id')}`: {item.get('summary')}")
    lines.extend(["", "## Checks not run", ""])
    skipped = report.get("checks_not_run", [])
    if isinstance(skipped, list):
        if not skipped:
            lines.append("- None.")
        for item in skipped:
            if isinstance(item, dict):
                column = item.get("column") or "(audit)"
                lines.append(f"- {item.get('check')} on {column}: {item.get('reason')}")
    lines.extend(
        [
            "",
            "## Feature inventory",
            "",
            "Roles are a classification, not a decision to train on every potential predictor.",
            "",
            "| Column | Role |",
            "| --- | --- |",
        ]
    )
    inventory = report.get("feature_inventory", [])
    if isinstance(inventory, list):
        for item in inventory:
            if isinstance(item, dict):
                lines.append(f"| {item.get('column')} | {item.get('role')} |")
    lines.extend(["", "## Column checks", ""])
    columns = report.get("columns", [])
    if isinstance(columns, list):
        lines.append("| Column | Missing rows | Unexpected codes | Coded missing |")
        lines.append("| --- | --- | --- | --- |")
        for item in columns:
            if isinstance(item, dict) and item.get("code_check") == "ran":
                lines.append(
                    f"| {item.get('name')} | {item.get('missing_rows')} | "
                    f"{item.get('unexpected_codes')} | {item.get('coded_missing_rows')} |"
                )
    lines.append("")
    return "\n".join(lines)


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, dict):
        return value
    raise TypeError("Audit section is not an object")
