"""
Tabular Profile Engine: profile-driven metadata extraction and row templating.

Replaces hard-coded field_map logic with configurable profiles for CSV/XLSX
ingestion. Profiles define:
- Column to metadata field mappings
- Content fields for chunk text
- Row text rendering templates
- Validation rules
"""

import logging
from typing import Any

import pandas as pd

from .cleaners import apply_cleaners

logger = logging.getLogger(__name__)


# Default profile for backward compatibility (replaces old field_map)
DEFAULT_SUPPORT_CASE_PROFILE = {
    "columns": [],
    "metadata_fields": {
        "Subject": "subject",
        "Description": "description",
        "Resolution": "resolution",
    },
    "content_fields": [],  # Empty means use all columns
    "required_fields": [],
    "validation_mode": "warn",
    "row_template": {
        "format": "key_value",
        "include_labels": True,
        "omit_empty": True,
        "field_order": None,
        "custom_template": None,
    },
}


class TabularProfileEngine:
    """
    Engine for processing tabular data according to an ingestion profile.

    Handles:
    - Row text rendering (how a row becomes chunk text)
    - Metadata extraction (which columns become filterable metadata)
    - Column aliasing and normalization
    - Validation
    """

    def __init__(self, profile_config: dict[str, Any] | None = None):
        """
        Initialize with a profile configuration.

        Args:
            profile_config: Profile config dict. Uses default if None.
        """
        self.config = profile_config or DEFAULT_SUPPORT_CASE_PROFILE
        self._column_aliases = self._build_alias_map()

    def _build_alias_map(self) -> dict[str, str]:
        """Build a mapping of aliases to canonical column names."""
        alias_map = {}
        columns = self.config.get("columns", [])
        for col_config in columns:
            canonical = col_config.get("name")
            if canonical:
                alias_map[canonical.lower()] = canonical
                for alias in col_config.get("aliases", []):
                    alias_map[alias.lower()] = canonical
        return alias_map

    def normalize_column_name(self, col_name: str) -> str:
        """
        Normalize a column name using aliases.

        Args:
            col_name: Raw column name from file

        Returns:
            Canonical column name (or original if no alias found)
        """
        return self._column_aliases.get(col_name.lower().strip(), col_name)

    def clean_value(self, val: Any, clean_data: bool = False) -> str | None:
        """
        Clean and normalize a cell value.

        Args:
            val: Raw cell value
            clean_data: Whether to apply content cleaners

        Returns:
            Cleaned string value, or None if empty/null
        """
        if pd.isna(val):
            return None

        # Convert to string, handling numeric types
        if isinstance(val, float) and val.is_integer():
            val_str = str(int(val))
        else:
            val_str = str(val)

        # Apply cleaners if requested
        if clean_data:
            val_str = apply_cleaners(val_str, enabled=True)

        return val_str.strip() if val_str.strip() else None

    def extract_metadata(
        self,
        row: pd.Series,
        clean_data: bool = False,
    ) -> dict[str, Any]:
        """
        Extract metadata fields from a row according to profile.

        Args:
            row: Pandas Series representing a row
            clean_data: Whether to apply content cleaners

        Returns:
            Dict of metadata key -> value
        """
        metadata = {}
        metadata_fields = self.config.get("metadata_fields", {})

        for col_name, meta_key in metadata_fields.items():
            # Try exact match first
            val = None
            if col_name in row.index:
                val = row[col_name]
            else:
                # Try normalized/aliased lookup
                normalized = self.normalize_column_name(col_name)
                if normalized in row.index:
                    val = row[normalized]

            cleaned = self.clean_value(val, clean_data)
            if cleaned:
                metadata[meta_key] = cleaned

        return metadata

    def render_row_text(
        self,
        row: pd.Series,
        columns: list[str],
        clean_data: bool = False,
    ) -> str:
        """
        Render a row as text according to the profile template.

        Args:
            row: Pandas Series representing a row
            columns: List of all column names in the dataframe
            clean_data: Whether to apply content cleaners

        Returns:
            Rendered text for the row
        """
        template = self.config.get("row_template", {})
        format_type = template.get("format", "key_value")
        include_labels = template.get("include_labels", True)
        omit_empty = template.get("omit_empty", True)
        field_order = template.get("field_order")

        # Determine which fields to include
        content_fields = self.config.get("content_fields", [])
        ordered_fields = None
        if isinstance(field_order, list) and len(field_order) > 0:
            ordered_fields = field_order

        # Prefer explicit ordering over content_fields (ordering is part of template UX)
        if ordered_fields:
            fields = ordered_fields
        elif content_fields:
            fields = content_fields
        else:
            fields = columns

        if format_type == "key_value":
            return self._render_key_value(
                row, fields, include_labels, omit_empty, clean_data
            )
        if format_type == "custom":
            custom_template = template.get("custom_template")
            if custom_template:
                return self._render_custom(row, custom_template, clean_data)
            # Fall back to key_value
            return self._render_key_value(
                row, fields, include_labels, omit_empty, clean_data
            )
        # Default to key_value
        return self._render_key_value(
            row, fields, include_labels, omit_empty, clean_data
        )

    def _render_key_value(
        self,
        row: pd.Series,
        fields: list[str],
        include_labels: bool,
        omit_empty: bool,
        clean_data: bool,
    ) -> str:
        """Render row as key: value pairs."""
        parts = []

        for field in fields:
            # Handle normalized column names
            actual_field = field
            if field not in row.index:
                normalized = self.normalize_column_name(field)
                if normalized in row.index:
                    actual_field = normalized
                else:
                    continue

            val = self.clean_value(row.get(actual_field), clean_data)

            if val is None or val == "":
                if omit_empty:
                    continue
                val = ""

            if include_labels:
                parts.append(f"{field}: {val}")
            else:
                parts.append(val)

        return "\n".join(parts)

    def _render_custom(
        self,
        row: pd.Series,
        template: str,
        clean_data: bool,
    ) -> str:
        """Render row using a Jinja2-style template (basic implementation)."""
        try:
            from jinja2 import Template

            # Prepare row data
            row_dict = {}
            for col in row.index:
                val = self.clean_value(row[col], clean_data)
                row_dict[col] = val if val else ""

            t = Template(template)
            return t.render(row=row_dict, **row_dict)
        except Exception as e:
            logger.warning(f"Failed to render custom template: {e}")
            # Fall back to simple representation
            return str(row.to_dict())

    def validate_row(
        self,
        row: pd.Series,
        row_index: int,
    ) -> tuple[bool, str | None]:
        """
        Validate a row against profile requirements.

        Args:
            row: Pandas Series representing a row
            row_index: Row number for error messages

        Returns:
            Tuple of (is_valid, error_message)
        """
        required_fields = self.config.get("required_fields", [])

        for field in required_fields:
            actual_field = field
            if field not in row.index:
                normalized = self.normalize_column_name(field)
                if normalized in row.index:
                    actual_field = normalized
                else:
                    return False, f"Row {row_index}: Missing required column '{field}'"

            if pd.isna(row[actual_field]) or str(row[actual_field]).strip() == "":
                return False, f"Row {row_index}: Required field '{field}' is empty"

        return True, None

    def process_dataframe(
        self,
        df: pd.DataFrame,
        sheet_name: str,
        file_path: str,
        file_type: str,
        original_filename: str,
        title: str,
        clean_data: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Process an entire dataframe into row chunks.

        Args:
            df: Input dataframe
            sheet_name: Sheet name (for metadata)
            file_path: File path (for metadata)
            file_type: File type (for metadata)
            original_filename: Original filename (for metadata)
            title: Document title (for metadata)
            clean_data: Whether to apply content cleaners

        Returns:
            List of row chunk dicts with 'content' and 'metadata' keys
        """
        validation_mode = self.config.get("validation_mode", "warn")

        # Normalize dataframe column names using profile aliases (so config can use canonical names)
        df = df.copy()
        df.columns = [str(c) for c in df.columns]

        if self._column_aliases:
            rename_map: dict[str, str] = {}
            used: set[str] = set()
            for raw_col in df.columns:
                canonical = self.normalize_column_name(raw_col)
                # Avoid collisions (keep original if already used)
                if canonical in used:
                    logger.warning(
                        "Tabular profile column collision: '%s' and another column both map to '%s'; keeping '%s' as-is",
                        raw_col,
                        canonical,
                        raw_col,
                    )
                    rename_map[raw_col] = raw_col
                    used.add(raw_col)
                else:
                    rename_map[raw_col] = canonical
                    used.add(canonical)
            df = df.rename(columns=rename_map)

        columns = list(df.columns)

        row_chunks = []
        skipped_count = 0

        for i, (_, row) in enumerate(df.iterrows()):
            # Preserve spreadsheet-style 1-based row numbers (row 1 is header)
            row_number = i + 2

            # Validate
            is_valid, error = self.validate_row(row, row_number)
            if not is_valid:
                if validation_mode == "fail":
                    raise ValueError(error)
                if validation_mode == "skip":
                    skipped_count += 1
                    continue
                # warn
                logger.warning(error)

            # Render row text
            row_text = self.render_row_text(row, columns, clean_data)
            if clean_data:
                row_text = apply_cleaners(row_text, enabled=True)

            if not row_text.strip():
                skipped_count += 1
                continue

            # Build metadata
            row_meta = {
                "sheet": sheet_name,
                "row_number": row_number,
                "file_path": file_path,
                "file_type": file_type,
                "display_name": title,
                "source_type": "file",
                "original_filename": original_filename,
            }

            # Extract profile-defined metadata
            extracted_meta = self.extract_metadata(row, clean_data)
            row_meta.update(extracted_meta)

            row_chunks.append(
                {
                    "content": row_text,
                    "metadata": row_meta,
                }
            )

        if skipped_count > 0:
            logger.info(f"Skipped {skipped_count} rows during processing")

        return row_chunks


def get_profile_engine(
    profile_config: dict[str, Any] | None = None,
) -> TabularProfileEngine:
    """
    Factory function to create a TabularProfileEngine.

    Args:
        profile_config: Profile configuration dict. Uses default if None.

    Returns:
        Configured TabularProfileEngine instance
    """
    return TabularProfileEngine(profile_config)
