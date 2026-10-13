"""A labeled stand-in classifier for API tests.

The positive probability is the longitude, or 0.4 when longitude is missing.
This is not the Phase 6 model.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


class LongitudeFixture:
    """Synthetic probability model. Joblib can reload this class in-process."""

    classes_ = np.array([0, 1])

    def predict_proba(self, frame):
        raw = pd.to_numeric(frame["longitude"], errors="coerce").to_numpy(dtype=float)
        positive = np.where(np.isnan(raw), 0.4, np.clip(raw, 0.0, 1.0))
        return np.column_stack([1.0 - positive, positive])
