"""
MNPI Expiration Date Management

Handles temporal MNPI governance:
  - Auto-assigns expiration dates (5-day rolling window)
  - Stores expiration as tags on tables
  - Polls for expired policies
  - Auto-drops expired policies

Expiration Date Formats:
  - ISO 8601 with timezone: "2024-12-31T23:59:59-05:00" (EST)
  - "never": Policy never expires
  - None/missing: Auto-assign 5 days from now
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger("abac_mvp2.mnpi_expiration")

# Default timezone for MNPI expiration
DEFAULT_TIMEZONE = "America/New_York"  # EST/EDT

# Default expiration window when none specified
DEFAULT_EXPIRATION_DAYS = 5


class MNPIExpirationManager:
    """
    Manages MNPI policy expiration dates.
    """

    def __init__(self, timezone: str = DEFAULT_TIMEZONE):
        """
        Args:
            timezone: IANA timezone name (e.g., "America/New_York" for EST)
        """
        self.timezone = ZoneInfo(timezone)

    def normalize_expiration_date(
        self,
        expiration_input: Optional[str],
        current_time: Optional[datetime] = None
    ) -> str:
        """
        Normalize expiration date to standard format.

        Args:
            expiration_input:
                - ISO 8601 datetime string: Use as-is
                - "never": No expiration
                - None: Auto-assign 5 days from now
            current_time: Override current time (for testing)

        Returns:
            - "never" for no expiration
            - ISO 8601 datetime string with timezone
        """
        if expiration_input == "never":
            return "never"

        if expiration_input is None:
            # Auto-assign 5 days from now
            if current_time is None:
                current_time = datetime.now(self.timezone)
            expiration = current_time + timedelta(days=DEFAULT_EXPIRATION_DAYS)
            return expiration.isoformat()

        # Parse and normalize existing date
        try:
            # Try parsing as ISO 8601
            dt = datetime.fromisoformat(expiration_input)
            # Ensure timezone
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=self.timezone)
            return dt.isoformat()
        except Exception as e:
            logger.warning(f"Invalid expiration date format '{expiration_input}': {e}")
            # Fallback: auto-assign
            if current_time is None:
                current_time = datetime.now(self.timezone)
            expiration = current_time + timedelta(days=DEFAULT_EXPIRATION_DAYS)
            return expiration.isoformat()

    def create_expiration_tag(self, expiration_date: str) -> Dict[str, str]:
        """
        Create expiration tag for table.

        Tag format: mnpi_expires = <ISO 8601 datetime or "never">

        Args:
            expiration_date: Normalized expiration date

        Returns:
            Dict with expiration tag
        """
        return {"mnpi_expires": expiration_date}

    def is_expired(
        self,
        expiration_date: str,
        current_time: Optional[datetime] = None
    ) -> bool:
        """
        Check if expiration date has passed.

        Args:
            expiration_date: Normalized expiration date string
            current_time: Override current time (for testing)

        Returns:
            True if expired, False otherwise
        """
        if expiration_date == "never":
            return False

        try:
            expiration_dt = datetime.fromisoformat(expiration_date)
            if current_time is None:
                current_time = datetime.now(self.timezone)
            return current_time >= expiration_dt
        except Exception as e:
            logger.error(f"Error checking expiration for '{expiration_date}': {e}")
            return False

    def get_expiration_from_tags(self, tags: Dict[str, str]) -> Optional[str]:
        """
        Extract expiration date from table tags.

        Args:
            tags: Table tags dict

        Returns:
            Expiration date string or None if not found
        """
        return tags.get("mnpi_expires")

    def extend_expiration(
        self,
        current_expiration: str,
        days: int = DEFAULT_EXPIRATION_DAYS,
        current_time: Optional[datetime] = None
    ) -> str:
        """
        Extend expiration by N days from current date.

        Args:
            current_expiration: Current expiration date
            days: Days to add
            current_time: Override current time (for testing)

        Returns:
            New expiration date (ISO 8601)
        """
        if current_expiration == "never":
            return "never"

        if current_time is None:
            current_time = datetime.now(self.timezone)

        new_expiration = current_time + timedelta(days=days)
        return new_expiration.isoformat()


def apply_expiration_dates_to_manifest(
    manifest: Any,
    timezone: str = DEFAULT_TIMEZONE
) -> Tuple[Any, Dict[str, int]]:
    """
    Apply expiration dates to all tables in manifest.

    - Tables with expiration_date: Use as-is
    - Tables with "never": No expiration
    - Tables without: Auto-assign 5 days from now

    Args:
        manifest: GovernanceManifest
        timezone: IANA timezone name

    Returns:
        Tuple of (updated manifest, stats)
    """
    manager = MNPIExpirationManager(timezone)
    stats = {
        "tables_with_expiration": 0,
        "tables_never_expire": 0,
        "tables_auto_assigned": 0,
    }

    for table in manifest.tables:
        # Only apply to tables with MNPI policies (direct OR inherited)
        all_bindings = list(table.policy_bindings) + list(getattr(table, 'inherited_policy_bindings', []))
        has_mnpi = any("mnpi" in policy.lower() for policy in all_bindings)
        if not has_mnpi:
            continue

        # Capture original value BEFORE normalizing (needed for stats)
        original_expiration = table.mnpi_expiration_date

        # Normalize expiration date
        normalized = manager.normalize_expiration_date(original_expiration)

        # Create expiration tag
        expiration_tag = manager.create_expiration_tag(normalized)

        # Merge with existing tags
        if table.tags is None:
            table.tags = {}
        table.tags.update(expiration_tag)

        # Update table expiration field
        table.mnpi_expiration_date = normalized

        # Track stats using original value (before overwrite on line above)
        if original_expiration == "never":
            stats["tables_never_expire"] += 1
        elif original_expiration is None:
            stats["tables_auto_assigned"] += 1
        else:
            stats["tables_with_expiration"] += 1

    logger.info(f"Applied expiration dates to manifest:")
    logger.info(f"  Explicit expiration: {stats['tables_with_expiration']}")
    logger.info(f"  Never expires: {stats['tables_never_expire']}")
    logger.info(f"  Auto-assigned (5 days): {stats['tables_auto_assigned']}")

    return manifest, stats
