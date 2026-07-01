"""Mapping of billing providers to dashboard categories.

A thin layer so the provider-agnostic pipeline can be sliced by category
(inference / training / later cloud) without any structural change.
"""

from __future__ import annotations

# provider -> category
PROVIDER_CATEGORY: dict[str, str] = {
    "runpod": "inference",
    "modal": "inference",
    "vastai": "training",
}

CATEGORIES: tuple[str, ...] = ("inference", "training")


def providers_in_category(category: str) -> list[str]:
    """Return the provider names belonging to a category (order-stable)."""
    if category not in CATEGORIES:
        raise ValueError(f"Unknown category '{category}'. Use one of: {CATEGORIES}.")
    return [p for p, c in PROVIDER_CATEGORY.items() if c == category]
