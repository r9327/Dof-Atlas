from __future__ import annotations

"""Canonical dependency surface for Guide Integrity.

Guide validation code should import through this module instead of versioned or
strict wrappers. This keeps the migration surface explicit and testable.
"""

from tools.guide_forensic import GuideForensicAudit
from tools.guide_gps import main as build_gps_route
from tools.validate_guide_ultime_manual_transversals import main as validate_transversals

__all__ = ("GuideForensicAudit", "build_gps_route", "validate_transversals")
