"""Leakage-safe feature transforms for collision severity.

The transforms are deterministic and do not fit encoders. Training is a
later phase.
"""

from roadrisk.features.spec import SPEC_VERSION, require_model_inputs
from roadrisk.features.split import assign_split
from roadrisk.features.transform import map_target, transform_row

__all__ = [
    "SPEC_VERSION",
    "assign_split",
    "map_target",
    "require_model_inputs",
    "transform_row",
]
