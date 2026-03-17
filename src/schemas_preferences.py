# ---------------------------------------------------------------------------
# DEPRECATED — moved to src/schemas/preferences.py
# This shim keeps backwards-compatibility for any external imports.
# Remove after confirming no other module references this path.
# ---------------------------------------------------------------------------
from src.schemas.preferences import (  # noqa: F401
    AggregatedPreferenceResponse,
    TenantPreferenceBase,
    TenantPreferenceResponse,
    TenantPreferenceUpdate,
    UserPreferenceBase,
    UserPreferenceResponse,
    UserPreferenceUpdate,
)
