"""
Cutoff engine – exact eligibility computation from Firestore.

This module NEVER approximates.  If data is missing it says so.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from google.cloud.firestore_v1.base_query import FieldFilter

from app.data.init_db import get_db, COLLECTION


@dataclass
class CutoffResult:
    eligible: Optional[bool] = None
    cutoff_rank: Optional[int] = None
    branch: Optional[str] = None
    category: Optional[str] = None
    year: Optional[int] = None
    round: Optional[int] = None
    gender: Optional[str] = None
    quota: Optional[str] = None
    message: str = ""
    all_results: list[dict] = field(default_factory=list)


def _normalise_branch(raw: str) -> str:
    """Best-effort normalisation of branch names."""
    mapping = {
        "computer science": "CSE",
        "computer": "CSE",
        "cse": "CSE",
        "cs": "CSE",
        "ece": "ECE",
        "electronics": "ECE",
        "eee": "EEE",
        "electrical": "EEE",
        "it": "IT",
        "information technology": "IT",
        "mech": "MECH",
        "mechanical": "MECH",
        "civil": "CIVIL",
        "ai": "CSE (AI & ML)",
        "ai ml": "CSE (AI & ML)",
        "ai & ml": "CSE (AI & ML)",
        "aiml": "CSE (AI & ML)",
        "artificial intelligence": "CSE (AI & ML)",
        "data science": "CSE (Data Science)",
        "ds": "CSE (Data Science)",
        "csd": "CSE (Data Science)",
    }
    return mapping.get(raw.strip().lower(), raw.strip().upper())


def _normalise_category(raw: str) -> str:
    mapping = {
        "oc": "OC",
        "general": "OC",
        "open": "OC",
        "obc": "BC-D",
        "bc-a": "BC-A",
        "bc-b": "BC-B",
        "bc-d": "BC-D",
        "bc-e": "BC-E",
        "bca": "BC-A",
        "bcb": "BC-B",
        "bcd": "BC-D",
        "bce": "BC-E",
        "sc": "SC",
        "st": "ST",
        "ews": "EWS",
    }
    return mapping.get(raw.strip().lower(), raw.strip().upper())


def get_cutoff(
    branch: str,
    category: str,
    year: int | None = None,
    round_num: int | None = None,
    gender: str = "Any",
    quota: str = "Convenor",
) -> CutoffResult:
    """
    Look up exact cutoff from Firestore.

    Parameters
    ----------
    branch : str  – e.g. "CSE", "ECE", "IT"
    category : str – e.g. "OC", "BC-A", "SC"
    year : int     – counselling year (defaults to latest available)
    round_num : int – counselling round (defaults to latest)
    gender : str   – "Any" | "Female"
    quota : str    – "Convenor" | "Management"
    """
    branch = _normalise_branch(branch)
    category = _normalise_category(category)

    db = get_db()
    query = db.collection(COLLECTION)

    # Build Firestore query with compound filters
    query = query.where(filter=FieldFilter("branch", "==", branch))
    query = query.where(filter=FieldFilter("category", "==", category))
    query = query.where(filter=FieldFilter("gender", "==", gender))
    query = query.where(filter=FieldFilter("quota", "==", quota))

    if year:
        query = query.where(filter=FieldFilter("year", "==", year))
    if round_num:
        query = query.where(filter=FieldFilter("round", "==", round_num))

    docs = query.stream()
    rows = [doc.to_dict() for doc in docs]

    # Sort: latest year first, then latest round
    rows.sort(key=lambda r: (r.get("year", 0), r.get("round", 0)), reverse=True)

    if not rows:
        return CutoffResult(
            branch=branch,
            category=category,
            year=year,
            round=round_num,
            message=(
                f"No cutoff data found for {branch} / {category}"
                + (f" / {year}" if year else "")
                + (f" / Round {round_num}" if round_num else "")
                + ". The data may not be available yet."
            ),
        )

    best = rows[0]

    return CutoffResult(
        cutoff_rank=best["cutoff_rank"],
        branch=best["branch"],
        category=best["category"],
        year=best["year"],
        round=best["round"],
        gender=best["gender"],
        quota=best["quota"],
        message=(
            f"The closing cutoff rank for {best['branch']} under {best['category']} "
            f"category in Year {best['year']}, Round {best['round']} "
            f"({best['quota']} quota) was **{best['cutoff_rank']:,}**."
        ),
        all_results=rows,
    )


def check_eligibility(
    rank: int,
    branch: str,
    category: str,
    year: int | None = None,
    round_num: int | None = None,
) -> CutoffResult:
    """
    Check if a given rank qualifies for a branch + category.
    Uses the latest available year/round if not specified.
    """
    result = get_cutoff(branch, category, year, round_num)

    if result.cutoff_rank is None:
        result.eligible = None
        return result

    result.eligible = rank <= result.cutoff_rank

    if result.eligible:
        result.message = (
            f"With a rank of **{rank:,}**, you are **eligible** for "
            f"{result.branch} under {result.category} category "
            f"(Year {result.year}, Round {result.round}, {result.quota} quota). "
            f"The closing rank was **{result.cutoff_rank:,}**."
        )
    else:
        result.message = (
            f"With a rank of **{rank:,}**, you are **not eligible** for "
            f"{result.branch} under {result.category} category "
            f"(Year {result.year}, Round {result.round}, {result.quota} quota). "
            f"The closing rank was **{result.cutoff_rank:,}**. "
            f"Your rank needs to be ≤ {result.cutoff_rank:,} for this seat."
        )

    return result


def list_branches() -> list[str]:
    """Return all distinct branches in Firestore."""
    db = get_db()
    docs = db.collection(COLLECTION).stream()
    branches = sorted({doc.to_dict().get("branch", "") for doc in docs})
    return [b for b in branches if b]


def list_categories() -> list[str]:
    """Return all distinct categories in Firestore."""
    db = get_db()
    docs = db.collection(COLLECTION).stream()
    cats = sorted({doc.to_dict().get("category", "") for doc in docs})
    return [c for c in cats if c]


def get_all_cutoffs_for_branch(
    branch: str, year: int | None = None
) -> list[dict]:
    """Return every document for a branch (all categories/rounds)."""
    branch = _normalise_branch(branch)
    db = get_db()
    query = db.collection(COLLECTION).where(
        filter=FieldFilter("branch", "==", branch)
    )

    if year:
        query = query.where(filter=FieldFilter("year", "==", year))

    docs = query.stream()
    rows = [doc.to_dict() for doc in docs]
    rows.sort(
        key=lambda r: (r.get("year", 0), r.get("category", ""), r.get("round", 0)),
        reverse=True,
    )
    return rows
