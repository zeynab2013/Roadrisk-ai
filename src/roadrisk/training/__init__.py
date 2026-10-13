"""Baseline training and the guarded Phase 6 evaluation.

Importing the estimators requires the ``ml`` extra. ``train`` and ``select``
do not score 2025. ``evaluate`` scores the frozen pipeline once. A valid
``test-evaluation.json`` blocks another score. Deleting or replacing that
file and the frozen decision removes the local record. The guard is not
tamper-proof.
"""
