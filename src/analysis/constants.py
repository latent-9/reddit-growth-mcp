"""Tunable thresholds for the analysis engine.

Centralised so the policy knobs live in one place rather than scattered as
magic numbers across modules.
"""

# Percentile that defines a "strong" post (used for timing hit-rate).
STRONG_PERCENTILE = 75
# Percentile that defines a "viral" (top-decile) post.
VIRAL_PERCENTILE = 90

# Removal-rate cutoffs for the safety label (mean-mod risk).
SAFETY_SAFE_MAX = 0.15
SAFETY_MODERATE_MAX = 0.35

# A title at or above this clickbait score counts as clickbaity.
CLICKBAIT_THRESHOLD = 0.4

# Above this share of AutoMod-filtered posts, a removal read is low-confidence.
LOW_CONFIDENCE_FILTERED_RATIO = 0.3

# Minimum posts a category/time bucket needs to be reported as reliable.
MIN_BUCKET_SAMPLES = 3
