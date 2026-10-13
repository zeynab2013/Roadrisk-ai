"""Code lists transcribed from the 2025 open-dataset data guide.

Source worksheet: ``2024_code_list``. The collision CSV uses
``enhanced_severity_collision`` for the guide's ``enhanced_collision_severity``.
``-1`` means "Data missing or out of range" wherever it appears below.
This module does not read the workbook at runtime.
"""

from __future__ import annotations

CODEBOOK_SOURCE = "dft-road-casualty-statistics-road-safety-open-dataset-data-guide-2025.xlsx"
CODEBOOK_SHEET = "2024_code_list"
MISSING_CODE = "-1"

# field -> allowed codes, including the missing sentinel when the guide defines it.
ALLOWED_CODES: dict[str, frozenset[str]] = {
    "collision_severity": frozenset({"1", "2", "3"}),
    "enhanced_severity_collision": frozenset({"1", "5", "6", "7", "3", "-1"}),
    "collision_injury_based": frozenset({"0", "1"}),
    "day_of_week": frozenset({"1", "2", "3", "4", "5", "6", "7"}),
    "first_road_class": frozenset({"1", "2", "3", "4", "5", "6", "-1"}),
    "second_road_class": frozenset({"0", "1", "2", "3", "4", "5", "6", "9", "-1"}),
    "road_type": frozenset({"1", "2", "3", "6", "7", "9", "12", "-1"}),
    # 20–70 are the public-highway values named in the speed_limit field note.
    # -1 and 99 are the coded rows in the same field.
    "speed_limit": frozenset({"20", "30", "40", "50", "60", "70", "99", "-1"}),
    "junction_detail": frozenset({"0", "13", "16", "17", "18", "19", "99", "-1"}),
    "junction_control": frozenset({"0", "1", "2", "3", "4", "9", "-1"}),
    "pedestrian_crossing": frozenset({"0", "11", "12", "13", "14", "15", "16", "17", "99", "-1"}),
    "light_conditions": frozenset({"1", "4", "5", "6", "7", "-1"}),
    "weather_conditions": frozenset({"1", "2", "3", "4", "5", "6", "7", "8", "9", "-1"}),
    "road_surface_conditions": frozenset({"1", "2", "3", "4", "5", "6", "7", "9", "-1"}),
    "special_conditions_at_site": frozenset({"0", "1", "2", "3", "4", "5", "6", "7", "9", "-1"}),
    "carriageway_hazards": frozenset(
        {"0", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "99", "-1"}
    ),
    "urban_or_rural_area": frozenset({"1", "2", "3", "-1"}),
    "trunk_road_flag": frozenset({"1", "2", "-1"}),
}

SEVERITY_LABELS = {"1": "Fatal", "2": "Serious", "3": "Slight"}
