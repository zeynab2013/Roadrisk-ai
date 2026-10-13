"""Feature specification version 1.

Approved names are the only model inputs. Conditional and excluded fields
are documented and are not emitted. Nothing here is fitted on data.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from roadrisk.data.errors import FeatureLeakageError
from roadrisk.data.schema import EXCLUDED_FROM_FEATURES, LABEL_COLUMN

SPEC_VERSION = 1
MISSING_TOKEN = "missing"
UNKNOWN_TOKEN = "unknown"
UNEXPECTED_TOKEN = "unexpected"

# Audit columns travel with the feature table. They are not model inputs.
AUDIT_COLUMNS: tuple[str, ...] = (
    "collision_index",
    "collision_year",
    "split",
    "collision_severity",
    "severity_serious_or_fatal",
)
LABEL_OUTPUT = "severity_serious_or_fatal"


@dataclass(frozen=True)
class FeatureField:
    """One source column and the decision made about it."""

    name: str
    source_column: str
    status: str
    meaning: str
    documentation: str
    data_type: str
    transformation: str
    missing_handling: str
    prediction_time_reason: str
    limitations: str


def _field(
    name: str,
    source_column: str,
    status: str,
    meaning: str,
    *,
    documentation: str,
    data_type: str,
    transformation: str,
    missing_handling: str,
    prediction_time_reason: str,
    limitations: str,
) -> FeatureField:
    return FeatureField(
        name=name,
        source_column=source_column,
        status=status,
        meaning=meaning,
        documentation=documentation,
        data_type=data_type,
        transformation=transformation,
        missing_handling=missing_handling,
        prediction_time_reason=prediction_time_reason,
        limitations=limitations,
    )


_GUIDE = "2025 open-dataset data guide, worksheet 2024_code_list"

APPROVED: tuple[FeatureField, ...] = (
    _field(
        "longitude",
        "longitude",
        "approved",
        "Longitude of the collision in decimal degrees.",
        documentation=_GUIDE,
        data_type="numeric",
        transformation="Keep the source text when it parses as a number.",
        missing_handling="Blank when the source is blank or not numeric. No imputed coordinate.",
        prediction_time_reason="The recorded location is part of the reported collision.",
        limitations="The audited extract has 53 rows with no coordinate. This is not exposure.",
    ),
    _field(
        "latitude",
        "latitude",
        "approved",
        "Latitude of the collision in decimal degrees.",
        documentation=_GUIDE,
        data_type="numeric",
        transformation="Keep the source text when it parses as a number.",
        missing_handling="Blank when the source is blank or not numeric. No imputed coordinate.",
        prediction_time_reason="The recorded location is part of the reported collision.",
        limitations="Paired with longitude. Easting and northing are not also approved.",
    ),
    _field(
        "hour",
        "time",
        "approved",
        "Hour of the collision, 0 to 23.",
        documentation=f"{_GUIDE}. Source format HH:MM.",
        data_type="numeric",
        transformation="Parse HH:MM and take the hour. The clock string is not a model input.",
        missing_handling="Blank when time is blank or not HH:MM.",
        prediction_time_reason="The collision time is an initial circumstance.",
        limitations="Minute is dropped. The year is not taken from this field.",
    ),
    _field(
        "weekday",
        "day_of_week",
        "approved",
        "Day of week. Codebook: 1 Sunday through 7 Saturday.",
        documentation=_GUIDE,
        data_type="categorical",
        transformation=(
            "Use day_of_week when it is 1 to 7. Otherwise derive it from a valid date. "
            "The raw date is not a model input."
        ),
        missing_handling="missing when neither the code nor the date yields a weekday.",
        prediction_time_reason="The collision date is known when the collision is reported.",
        limitations="A valid day_of_week is kept even if it disagrees with the date.",
    ),
    _field(
        "month",
        "date",
        "approved",
        "Month of the collision, 1 to 12.",
        documentation=f"{_GUIDE}. Source format DD/MM/YYYY.",
        data_type="numeric",
        transformation="Parse DD/MM/YYYY and take the month. The year is not a model input.",
        missing_handling="Blank when the date is blank or invalid.",
        prediction_time_reason="The collision date is an initial circumstance.",
        limitations="Month does not identify the train, validation, or test year.",
    ),
    _field(
        "season",
        "date",
        "approved",
        "Meteorological season from the collision month.",
        documentation="Derived from the collision date. Winter is December to February.",
        data_type="categorical",
        transformation="Map month to winter, spring, summer, or autumn.",
        missing_handling="Blank when the date does not yield a month.",
        prediction_time_reason="Season is a function of the collision date only.",
        limitations="This is not a weather observation. weather_conditions carries that.",
    ),
    _field(
        "first_road_class",
        "first_road_class",
        "approved",
        "Class of the first road, from motorway to unclassified.",
        documentation=_GUIDE,
        data_type="categorical",
        transformation="Keep a codebook value. Do not use the road number.",
        missing_handling="missing for blank or -1. unexpected for any other unknown code.",
        prediction_time_reason="Road class is a property of the place the collision was reported.",
        limitations="first_road_number is conditional and is not used.",
    ),
    _field(
        "road_type",
        "road_type",
        "approved",
        "Road layout, such as roundabout, dual carriageway, or single carriageway.",
        documentation=_GUIDE,
        data_type="categorical",
        transformation="Keep a codebook value. Code 9 is the unknown token.",
        missing_handling="missing for blank or -1. unknown for code 9.",
        prediction_time_reason="The layout is recorded with the collision circumstances.",
        limitations="Code 12 is a combined one-way and slip-road value and stays as 12.",
    ),
    _field(
        "speed_limit",
        "speed_limit",
        "approved",
        "Posted speed limit. Valid public-highway values are 20, 30, 40, 50, 60, and 70.",
        documentation=f"{_GUIDE}. The field note lists those six limits. 99 is unknown.",
        data_type="categorical",
        transformation="Keep the code. Do not treat the limit as a mean-imputed number.",
        missing_handling="missing for blank or -1. unknown for code 99.",
        prediction_time_reason="The posted limit is a road attribute, not an outcome.",
        limitations="The audited extract has no code 99. Three rows are -1.",
    ),
    _field(
        "junction_detail",
        "junction_detail",
        "approved",
        "Junction type on the 2024 STATS19 code list.",
        documentation=(
            f"{_GUIDE}. The guide says this field was added with the 2024 data "
            "and that earlier rows were converted to that specification."
        ),
        data_type="categorical",
        transformation="Use this column only. Ignore junction_detail_historic.",
        missing_handling="missing for blank or -1. unknown for code 99.",
        prediction_time_reason="Junction type is a circumstance of the reported site.",
        limitations="The historic code list is a different schema and is excluded.",
    ),
    _field(
        "junction_control",
        "junction_control",
        "approved",
        "How the junction is controlled, including give way and traffic signals.",
        documentation=_GUIDE,
        data_type="categorical",
        transformation="Keep a codebook value.",
        missing_handling="missing for blank or -1. unknown for code 9.",
        prediction_time_reason="Junction control is recorded with the collision circumstances.",
        limitations="Code 0 means not at a junction. It is a real state, not missing.",
    ),
    _field(
        "second_road_class",
        "second_road_class",
        "approved",
        "Class of the second road when the collision is at a junction.",
        documentation=_GUIDE,
        data_type="categorical",
        transformation="Keep a codebook value. Do not use the second road number.",
        missing_handling="missing for blank or -1. unknown for code 9.",
        prediction_time_reason="The second road is part of the junction description.",
        limitations="Code 0 means not at a junction. second_road_number stays conditional.",
    ),
    _field(
        "pedestrian_crossing",
        "pedestrian_crossing",
        "approved",
        "Physical crossing facility on the 2024 STATS19 code list.",
        documentation=(
            f"{_GUIDE}. The guide says this field was added with the 2024 data "
            "and that earlier rows were converted to that specification."
        ),
        data_type="categorical",
        transformation="Use this column only. Ignore the historic crossing columns.",
        missing_handling="missing for blank or -1. unknown for code 99.",
        prediction_time_reason="A crossing facility is a site circumstance.",
        limitations="Historic human-control and physical-facility columns are excluded.",
    ),
    _field(
        "light_conditions",
        "light_conditions",
        "approved",
        "Daylight or darkness, and whether street lighting was lit.",
        documentation=_GUIDE,
        data_type="categorical",
        transformation="Keep a codebook value, including code 7 (darkness, lighting unknown).",
        missing_handling="missing for blank or -1. Code 7 stays 7.",
        prediction_time_reason="Light is an observed circumstance at the collision time.",
        limitations="Code 7 is an observed unknown lighting state, not a blank field.",
    ),
    _field(
        "weather_conditions",
        "weather_conditions",
        "approved",
        "Weather recorded for the collision, including rain, snow, fog, and wind.",
        documentation=_GUIDE,
        data_type="categorical",
        transformation="Keep a codebook value. Code 9 is the unknown token.",
        missing_handling="missing for blank or -1. unknown for code 9.",
        prediction_time_reason="Weather is an initial circumstance, not a casualty outcome.",
        limitations="This is a reported category, not a measurement from a weather station.",
    ),
    _field(
        "road_surface_conditions",
        "road_surface_conditions",
        "approved",
        "Road surface state, such as dry, wet, snow, or ice.",
        documentation=_GUIDE,
        data_type="categorical",
        transformation="Keep a codebook value. Code 9 is the unknown token.",
        missing_handling="missing for blank or -1. unknown for code 9.",
        prediction_time_reason="Surface condition is recorded with the collision circumstances.",
        limitations="It is not a substitute for weather_conditions.",
    ),
    _field(
        "special_conditions_at_site",
        "special_conditions_at_site",
        "approved",
        "Site conditions such as roadworks, a defective signal, or a defective sign.",
        documentation=_GUIDE,
        data_type="categorical",
        transformation="Keep a codebook value. Code 9 is the unknown token.",
        missing_handling="missing for blank or -1. unknown for code 9.",
        prediction_time_reason="Site conditions are on the collision record, not casualty counts.",
        limitations="The audit found code -1 on a large share of rows. Those stay missing.",
    ),
    _field(
        "urban_or_rural_area",
        "urban_or_rural_area",
        "approved",
        "Urban, rural, or unallocated. Codebook codes 1, 2, and 3.",
        documentation=f"{_GUIDE}. Field introduced in 1994.",
        data_type="categorical",
        transformation="Keep a codebook value. Code 3 (unallocated) stays 3.",
        missing_handling="missing for blank or -1.",
        prediction_time_reason="The urban or rural class is a property of the recorded location.",
        limitations="Unallocated is unusual and allowed. It is not recoded.",
    ),
    _field(
        "trunk_road_flag",
        "trunk_road_flag",
        "approved",
        "Whether the road is a trunk road. Code 1 trunk, code 2 non-trunk.",
        documentation=_GUIDE,
        data_type="categorical",
        transformation="Keep a codebook value.",
        missing_handling="missing for blank or -1.",
        prediction_time_reason="Trunk status is a road-network attribute, not an outcome.",
        limitations="Code 1 is still labelled Highways England. The flag means trunk or not.",
    ),
)

CONDITIONAL: tuple[FeatureField, ...] = (
    _field(
        "location_easting_osgr",
        "location_easting_osgr",
        "conditional",
        "British National Grid easting.",
        documentation=_GUIDE,
        data_type="numeric",
        transformation="Not emitted. Longitude is the approved horizontal coordinate.",
        missing_handling="Not applicable until a coordinate-reference decision is made.",
        prediction_time_reason="The grid reference is the same location as longitude and latitude.",
        limitations="Using both coordinate systems would duplicate the location.",
    ),
    _field(
        "location_northing_osgr",
        "location_northing_osgr",
        "conditional",
        "British National Grid northing.",
        documentation=_GUIDE,
        data_type="numeric",
        transformation="Not emitted. Latitude is the approved vertical coordinate.",
        missing_handling="Not applicable until a coordinate-reference decision is made.",
        prediction_time_reason="The grid reference is the same location as longitude and latitude.",
        limitations="Same open decision as easting.",
    ),
    _field(
        "carriageway_hazards",
        "carriageway_hazards",
        "conditional",
        "Objects or defects in the carriageway on the 2024 code list.",
        documentation=(
            f"{_GUIDE}. Codes include roadworks and also "
            "'Involvement with previous collision'."
        ),
        data_type="categorical",
        transformation="Not emitted.",
        missing_handling="Not applicable while the field is conditional.",
        prediction_time_reason="Some codes are site conditions. Others name a previous collision.",
        limitations="Hazards and prior-collision codes are unresolved, so this stays conditional.",
    ),
    _field(
        "police_force",
        "police_force",
        "conditional",
        "Police force that recorded the collision.",
        documentation=_GUIDE,
        data_type="categorical",
        transformation="Not emitted.",
        missing_handling="Not applicable while the field is conditional.",
        prediction_time_reason="The force is an administrative reporter, not a road circumstance.",
        limitations="It may proxy the injury-based reporting change. That use is not approved.",
    ),
    _field(
        "local_authority_ons_district",
        "local_authority_ons_district",
        "conditional",
        "ONS district code for the collision location.",
        documentation=_GUIDE,
        data_type="categorical",
        transformation="Not emitted.",
        missing_handling="Not applicable while the field is conditional.",
        prediction_time_reason="The code is an administrative area, not a physical road attribute.",
        limitations="High cardinality. Not approved. The older district code is excluded.",
    ),
    _field(
        "local_authority_highway",
        "local_authority_highway",
        "conditional",
        "Highway authority code recorded for the collision.",
        documentation=_GUIDE,
        data_type="categorical",
        transformation="Not emitted.",
        missing_handling="Not applicable while the field is conditional.",
        prediction_time_reason="An administrative authority, not an approved road attribute.",
        limitations="The current-boundary remap is excluded. This recorded code stays conditional.",
    ),
    _field(
        "first_road_number",
        "first_road_number",
        "conditional",
        "Number of the first road.",
        documentation=_GUIDE,
        data_type="categorical",
        transformation="Not emitted. first_road_class is the approved road identity.",
        missing_handling="Not applicable while the field is conditional.",
        prediction_time_reason="A road number identifies one road. It is not approved.",
        limitations="High cardinality. Not approved.",
    ),
    _field(
        "second_road_number",
        "second_road_number",
        "conditional",
        "Number of the second road.",
        documentation=_GUIDE,
        data_type="categorical",
        transformation="Not emitted. second_road_class is the approved field.",
        missing_handling="Not applicable while the field is conditional.",
        prediction_time_reason="Same open decision as the first road number.",
        limitations="High cardinality. Not approved.",
    ),
)

def _excluded(
    name: str,
    meaning: str,
    *,
    reason: str,
) -> FeatureField:
    return _field(
        name,
        name,
        "excluded",
        meaning,
        documentation=_GUIDE,
        data_type="not a predictor",
        transformation="Not emitted as a model input.",
        missing_handling="Not used.",
        prediction_time_reason=reason,
        limitations=reason,
    )


EXCLUDED: tuple[FeatureField, ...] = (
    _excluded(
        "collision_index",
        "Collision identifier.",
        reason="An identifier used only to reconcile rows. It is not a predictor.",
    ),
    _excluded(
        "collision_ref_no",
        "Reference number within the reporting system.",
        reason="An administrative identifier. It is not a predictor.",
    ),
    _excluded(
        "collision_year",
        "Year used to assign the temporal split.",
        reason="The split key. Using it as a feature would identify the holdout year.",
    ),
    _excluded(
        "date",
        "Collision date.",
        reason="The raw date contains the year. month and season are the model inputs.",
    ),
    _excluded(
        "time",
        "Collision time.",
        reason="The raw clock is replaced by hour.",
    ),
    _excluded(
        "collision_severity",
        "Recorded severity. Codes 1 Fatal, 2 Serious, and 3 Slight.",
        reason="This is the target. The mapped label is severity_serious_or_fatal.",
    ),
    _excluded(
        "number_of_vehicles",
        "Vehicles involved in the collision.",
        reason="A count produced by the collision, not an initial circumstance.",
    ),
    _excluded(
        "number_of_casualties",
        "Casualties in the collision.",
        reason="A casualty outcome. It is unavailable as a predictor of severity.",
    ),
    _excluded(
        "did_police_officer_attend_scene_of_accident",
        "Whether an officer attended.",
        reason="Post-event operational reporting, not a road circumstance.",
    ),
    _excluded(
        "enhanced_severity_collision",
        "Finer injury-based severity scale.",
        reason="Target-derived. It is not interchangeable with collision_severity.",
    ),
    _excluded(
        "collision_injury_based",
        "Flag for injury-based versus severity reporting.",
        reason="Describes how the target was recorded. It is not a predictor.",
    ),
    _excluded(
        "collision_adjusted_severity_serious",
        "DfT serious-severity adjustment weight.",
        reason="A target weight, not a class label and not a predictor.",
    ),
    _excluded(
        "collision_adjusted_severity_slight",
        "DfT slight-severity adjustment weight.",
        reason="A target weight, not a class label and not a predictor.",
    ),
    _excluded(
        "local_authority_district",
        "Older district code.",
        reason="Code -1 is deprecated on almost every audited row. It is not a predictor.",
    ),
    _excluded(
        "local_authority_highway_current",
        "Highway authority remapped to the latest ONS code list.",
        reason=(
            "The guide says this field arrived with the 2024 data and maps all "
            "collisions onto the latest list. That is a later geography, so it is excluded."
        ),
    ),
    _excluded(
        "junction_detail_historic",
        "Junction type on the 2011 specification.",
        reason="A superseded schema that overlaps junction_detail. It is not a second predictor.",
    ),
    _excluded(
        "pedestrian_crossing_human_control_historic",
        "Historic human crossing control.",
        reason="Superseded by pedestrian_crossing. The schemas are not combined.",
    ),
    _excluded(
        "pedestrian_crossing_physical_facilities_historic",
        "Historic physical crossing facility.",
        reason="Superseded by pedestrian_crossing. The schemas are not combined.",
    ),
    _excluded(
        "carriageway_hazards_historic",
        "Historic carriageway hazards.",
        reason="Superseded schema. The current hazards field is still only conditional.",
    ),
    _excluded(
        "lsoa_of_accident_location",
        "Lower-layer super output area.",
        reason="A small-area identifier, and the audit notes it covers England and Wales only.",
    ),
)

CATALOG: tuple[FeatureField, ...] = APPROVED + CONDITIONAL + EXCLUDED

# Codes the guide labels as unknown, distinct from -1 (missing or out of range).
UNKNOWN_CODES: dict[str, frozenset[str]] = {
    "road_type": frozenset({"9"}),
    "speed_limit": frozenset({"99"}),
    "junction_detail": frozenset({"99"}),
    "junction_control": frozenset({"9"}),
    "second_road_class": frozenset({"9"}),
    "pedestrian_crossing": frozenset({"99"}),
    "weather_conditions": frozenset({"9"}),
    "road_surface_conditions": frozenset({"9"}),
    "special_conditions_at_site": frozenset({"9"}),
}

APPROVED_NAMES: tuple[str, ...] = tuple(field.name for field in APPROVED)
APPROVED_SOURCES: tuple[str, ...] = tuple(dict.fromkeys(field.source_column for field in APPROVED))
MODEL_INPUTS: frozenset[str] = frozenset(APPROVED_NAMES)


def fields_with_status(status: str) -> tuple[FeatureField, ...]:
    """Return catalog entries with one status."""

    return tuple(field for field in CATALOG if field.status == status)


def require_model_inputs(names: Sequence[str]) -> None:
    """Raise when a proposed model input is outside the approved allowlist."""

    blocked = set(EXCLUDED_FROM_FEATURES) | {LABEL_COLUMN, LABEL_OUTPUT}
    leaked = tuple(name for name in names if name in blocked)
    if leaked:
        raise FeatureLeakageError(
            "These columns are excluded from model inputs: " + ", ".join(leaked)
        )
    rejected = tuple(name for name in names if name not in MODEL_INPUTS)
    if rejected:
        raise FeatureLeakageError(
            "These columns are not approved model inputs: " + ", ".join(rejected)
        )
