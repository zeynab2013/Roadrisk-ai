"""RoadRisk library.

``roadrisk.data`` checks the collision catalog, file digests, and table
headers. ``roadrisk.features`` builds the leakage-safe feature table.
``roadrisk.training`` fits the baseline comparison and the Phase 6
calibration and threshold choice. ``roadrisk.inference`` explains the
frozen severity model and assigns research probability bands. The HTTP
service lives in ``apps/api`` and is not imported by this package. Neither
path rescores 2025.
"""

__version__: str = "0.1.0"
