"""Open Knowledge Format (OKF) v0.2 helpers.

The implementation deliberately validates only the structural contract from
the specification. Producer-defined frontmatter extensions are preserved.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import frontmatter

OKF_VERSION = "0.2"
OKF_STATUSES = {"draft", "stable", "deprecated"}


def _is_iso8601(value: Any) -> bool:
    if isinstance(value, datetime):
        return value.tzinfo is not None
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def validate_concept(text: str) -> list[str]:
    """Return OKF v0.2 validation errors without rejecting extensions."""
    try:
        post = frontmatter.loads(text)
    except Exception as exc:
        return [f"invalid YAML frontmatter: {exc}"]

    errors: list[str] = []
    if not isinstance(post.get("type"), str) or not post.get("type", "").strip():
        errors.append("missing required frontmatter field: type")

    status = post.get("status")
    if status is not None and status not in OKF_STATUSES:
        errors.append("status must be draft, stable, or deprecated")

    generated = post.get("generated")
    if generated is not None:
        if not isinstance(generated, dict) or not generated.get("by") or not _is_iso8601(generated.get("at")):
            errors.append("generated requires by and an ISO 8601 at")

    verified = post.get("verified")
    if isinstance(verified, dict):
        verified = [verified]
    if verified is not None:
        if not isinstance(verified, list):
            errors.append("verified must be a mapping or list of mappings")
        else:
            for item in verified:
                if not isinstance(item, dict) or not item.get("by") or not _is_iso8601(item.get("at")):
                    errors.append("each verified entry requires by and an ISO 8601 at")

    sources = post.get("sources")
    if sources is not None:
        if not isinstance(sources, list):
            errors.append("sources must be a list")
        else:
            for item in sources:
                if not isinstance(item, dict) or not item.get("resource"):
                    errors.append("each sources entry requires resource")

    if post.get("stale_after") is not None and not _is_iso8601(post["stale_after"]):
        errors.append("stale_after must be an ISO 8601 datetime")

    if post.get("type") == "Attested Computation":
        if not isinstance(post.get("runtime"), str) or not post["runtime"].strip():
            errors.append("Attested Computation requires runtime")

    return errors


def normalize_concept(text: str) -> str:
    """Validate and return a lossless OKF document.

    Unknown fields and the Markdown body are intentionally untouched.
    """
    errors = validate_concept(text)
    if errors:
        raise ValueError("; ".join(errors))
    return text
