"""
Lightweight text cleaning utilities for RAG ingestion.

Currently removes common email/security banners, inline CID image tags,
collapses excessive blank lines, and strips surrounding quotes.
"""

from __future__ import annotations

import html
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

# Patterns to drop low-signal boilerplate from uploads (e.g., ticket exports, emails)
SECURITY_BANNER = re.compile(
    r"^warning:\s*this email originated outside.*?$",
    re.IGNORECASE | re.MULTILINE,
)
CID_TAG = re.compile(r"\[cid:[^\]]+\]", re.IGNORECASE)
MULTI_NEWLINES = re.compile(r"\n{3,}")


def _strip_security_banner(text: str) -> str:
    return SECURITY_BANNER.sub("", text)


def _strip_cid_tags(text: str) -> str:
    return CID_TAG.sub("", text)


def _collapse_newlines(text: str) -> str:
    return MULTI_NEWLINES.sub("\n\n", text)


def _strip_quotes(text: str) -> str:
    return text.strip().strip('"').strip("'")


DEFAULT_CLEANERS: tuple[Callable[[str], str], ...] = (
    html.unescape,
    _strip_security_banner,
    _strip_cid_tags,
    _collapse_newlines,
    _strip_quotes,
)


def apply_cleaners(
    text: str | None,
    enabled: bool = True,
    cleaners: Iterable[Callable[[str], str]] | None = None,
) -> str:
    """
    Apply a pipeline of cleaners to text. If disabled, returns the original text.
    """
    if not enabled:
        return "" if text is None else str(text)

    pipeline = list(cleaners) if cleaners else list(DEFAULT_CLEANERS)
    cleaned = "" if text is None else str(text)
    for fn in pipeline:
        cleaned = fn(cleaned)
    return cleaned.strip()
