"""
Cutoff engine – exact eligibility computation from Firestore.

This module NEVER approximates.  If data is missing it says so.
"""

from __future__ import annotations

import logging
import sys
import traceback

logger = logging.getLogger("app.logic.cutoff_engine")
logger.info("cutoff_engine.py: starting imports...")

from dataclasses import dataclass, field
from typing import Optional

logger.info("cutoff_engine.py: importing google.cloud.firestore_v1...")
try:
    from google.cloud.firestore_v1.base_query import FieldFilter
    logger.info("cutoff_engine.py: google.cloud.firestore_v1 OK")
except Exception as e:
    logger.error(f"cutoff_engine.py: FAILED google.cloud.firestore_v1: {e}")
    traceback.print_exc()
    raise

logger.info("cutoff_engine.py: importing init_db...")
try:
    from app.data.init_db import get_db, COLLECTION
    logger.info("cutoff_engine.py: init_db OK")
except Exception as e:
    logger.error(f"cutoff_engine.py: FAILED init_db: {e}")
    traceback.print_exc()
    raise

logger.info("cutoff_engine.py: importing config...")
try:
    from app.config import get_settings
    logger.info("cutoff_engine.py: config OK")
except Exception as e:
    logger.error(f"cutoff_engine.py: FAILED config: {e}")
    traceback.print_exc()
    raise


@dataclass
class CutoffResult:
    eligible: Optional[bool] = None
    found: Optional[bool] = None
    cutoff_rank: Optional[int] = None   # closing / last rank
    first_rank: Optional[int] = None   # opening / first rank
    last_rank: Optional[int] = None    # alias for cutoff_rank (closing rank)
    branch: Optional[str] = None
    category: Optional[str] = None
    year: Optional[int] = None
    round: Optional[int] = None
    gender: Optional[str] = None
    quota: Optional[str] = None
    message: str = ""
    all_results: list[dict] = field(default_factory=list)


def _get_department_url(branch: str) -> str | None:
    """
    Get the department URL for a given branch.
    Maps normalized branch codes to department pages.
    """
    settings = get_settings()
    dept_urls = settings.DEPARTMENT_URLS
    
    # Mapping of branch codes to department URL keys
    branch_mapping = {
        # CSE variants
        "CSE": "cse",
        "CSB": "cse",  # CS & Business Systems under CSE
        
        # AI/ML/IoT specializations
        "CSE-CSM": "cse_aiml_iot",  # AI & ML
        "CSE-CSO": "cse_aiml_iot",  # IoT
        "RAI": "cse_aiml_iot",      # Robotics & AI
        
        # Data Science/Cyber Security
        "CSE-CSD": "cse_ds_cys",  # Data Science
        "AID": "cse_ds_cys",       # AI & Data Science
        "CSE-CSC": "cse_ds_cys",  # Cyber Security
        
        # Other departments
        "IT": "it",
        "ME": "mech",
        "AUT": "automobile",  # Automobile Engineering
        "BIO": "biotechnology",  # Biotechnology
        "CIV": "civil",
        "ECE": "ece",
        "EEE": "eee",
        "EIE": "eie",
    }
    
    dept_key = branch_mapping.get(branch)
    if dept_key:
        return dept_urls.get(dept_key)
    return None


def _normalise_branch(raw: str) -> str:
    """Best-effort normalisation of branch names."""
    mapping = {
        "computer science": "CSE",
        "computer": "CSE",
        "cse": "CSE",
        "cs": "CSE",
        "ece": "ECE",
        "electronics": "ECE",
        "electronics communication": "ECE",
        "eee": "EEE",
        "electrical": "EEE",
        "electrical electronics": "EEE",
        "it": "IT",
        "information technology": "IT",
        "mech": "ME",
        "me": "ME",
        "mechanical": "ME",
        "civil": "CIV",
        "civ": "CIV",
        
        # AI & ML variants (CSE-CSM)
        "ai ml": "CSE-CSM",
        "ai & ml": "CSE-CSM",
        "aiml": "CSE-CSM",
        "ai and ml": "CSE-CSM",
        "artificial intelligence ml": "CSE-CSM",
        "artificial intelligence machine learning": "CSE-CSM",
        "artificial intelligence and machine learning": "CSE-CSM",
        "machine learning": "CSE-CSM",
        
        # AI & Data Science variants (AID)
        "ai & ds": "AID",
        "ai ds": "AID",
        "aids": "AID",
        "ai and ds": "AID",
        "ai & data science": "AID",
        "ai and data science": "AID",
        "artificial intelligence data science": "AID",
        "artificial intelligence and data science": "AID",
        
        # Data Science variants (CSE-CSD)
        "data science": "CSE-CSD",
        "ds": "CSE-CSD",
        "csd": "CSE-CSD",
        "cse-csd": "CSE-CSD",
        "cse csd": "CSE-CSD",
        "cse (data science)": "CSE-CSD",
        
        # AI/ML/IoT combined
        "csm": "CSE-CSM",
        "cse-csm": "CSE-CSM",
        "cse csm": "CSE-CSM",
        "cse (ai & ml)": "CSE-CSM",
        
        # Cyber Security
        "csc": "CSE-CSC",
        "cse-csc": "CSE-CSC",
        "cse csc": "CSE-CSC",
        "cyber security": "CSE-CSC",
        "cys": "CSE-CSC",
        "cybersecurity": "CSE-CSC",
        
        # IoT
        "cso": "CSE-CSO",
        "cse-cso": "CSE-CSO",
        "cse cso": "CSE-CSO",
        "iot": "CSE-CSO",
        "internet of things": "CSE-CSO",
        
        # Business Systems
        "csb": "CSB",
        "cs business": "CSB",
        "business systems": "CSB",
        "aid": "AID",
        "aut": "AUT",
        "automobile": "AUT",
        "bio": "BIO",
        "biotech": "BIO",
        "biotechnology": "BIO",
        "eie": "EIE",
        "rai": "RAI",
        "robotics": "RAI",
        "robotics & ai": "RAI",
        "vlsi": "VLSI",
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
        "bc-c": "BC-C",
        "bc-d": "BC-D",
        "bc-e": "BC-E",
        "bca": "BC-A",
        "bcb": "BC-B",
        "bcc": "BC-C",
        "bcd": "BC-D",
        "bce": "BC-E",
        "sc": "SC",
        "sc-i": "SC-I",
        "sc-ii": "SC-II",
        "sc-iii": "SC-III",
        "sc-1": "SC-I",
        "sc-2": "SC-II",
        "sc-3": "SC-III",
        "sc1": "SC-I",
        "sc2": "SC-II",
        "sc3": "SC-III",
        "st": "ST",
        "ews": "EWS",
    }
    return mapping.get(raw.strip().lower(), raw.strip().upper())


def _resolve_rank_fields(row: dict) -> None:
    """
    Normalise rank field names in-place so every row exposes:
      - first_rank  (opening rank)  — None when not stored in Firestore
      - last_rank   (closing/cutoff rank)
      - cutoff_rank (alias for last_rank, used for eligibility checks)

    Firestore documents may store these under several historic field names.
    This function accepts any combination and always fills last_rank /
    cutoff_rank, but leaves first_rank as None when the source data does
    not contain it (avoids duplicating the closing rank into the opening rank).
    """
    # ── Resolve last_rank (closing/cutoff rank) ───────────────
    # Priority: last_rank field > cutoff_rank field > first_rank (last resort)
    if "last_rank" not in row:
        if "cutoff_rank" in row:
            row["last_rank"] = row["cutoff_rank"]
        elif "first_rank" in row:
            # Only one rank present — treat it as the closing rank
            row["last_rank"] = row["first_rank"]

    # ── Resolve cutoff_rank (alias for last_rank) ───────────────
    if "cutoff_rank" not in row:
        row["cutoff_rank"] = row.get("last_rank")

    # ── first_rank: only set when explicitly provided in the document ───────
    # Do NOT fall back to cutoff_rank — that causes the "same value" bug.
    # Callers should check `row.get("first_rank")` and handle None gracefully.

    # ── Ensure all stored values are proper integers or None ──────────────
    for fld in ("first_rank", "last_rank", "cutoff_rank"):
        val = row.get(fld)
        if val is not None:
            try:
                row[fld] = int(val)
            except (TypeError, ValueError):
                row[fld] = None


def get_cutoff(
    branch: str,
    category: str,
    year: int | None = None,
    round_num: int | None = None,
    gender: str = "Any",
    quota: str = "Convenor",
    ph_type: str | None = None,
    show_trend: bool = False,
) -> CutoffResult:
    """
    Look up exact cutoff from Firestore.

    Parameters
    ----------
    branch : str  – e.g. "CSE", "ECE", "IT"
    category : str – e.g. "OC", "BC-A", "SC"
    year : int     – counselling year (defaults to latest available)
    round_num : int – counselling round (defaults to latest)
    gender : str   – "Boys" | "Girls"
    quota : str    – "Convenor" | "SPORTS" | "CAP" | "NCC" | "OTHERS"
    ph_type : str  – PH disability code: "PHV","PHH","PHO","PHM","PHA" or None
    show_trend : bool – If True, show all years with trend analysis; if False, show only latest year
    """
    logger.info(f"get_cutoff called: branch={branch}, category={category}, year={year}, gender={gender}, quota={quota}")
    branch = _normalise_branch(branch)
    category = _normalise_category(category)

    db = get_db()
    if db is None:
        logger.warning("Firestore not available. Cannot query cutoff data.")
        return CutoffResult(
            message="WARNING: Cutoff database is currently unavailable. Please try general admission questions instead, or contact admissionsenquiry@vnrvjiet.in for cutoff information.",
            found=False,
        )

    query = db.collection(COLLECTION)

    # Build Firestore query with compound filters
    query = query.where(filter=FieldFilter("branch", "==", branch))
    query = query.where(filter=FieldFilter("category", "==", category))
    # Only filter by gender when a specific gender is requested.
    # "Any" / None means "show both Boys and Girls" — omitting the filter
    # returns all matching rows so the caller can pick the best one.
    _gender_specific = gender and gender not in ("Any", "ALL")
    if _gender_specific:
        query = query.where(filter=FieldFilter("gender", "==", gender))
    query = query.where(filter=FieldFilter("quota", "==", quota))

    if ph_type:
        query = query.where(filter=FieldFilter("ph_type", "==", ph_type))

    if year:
        query = query.where(filter=FieldFilter("year", "==", year))
    if round_num:
        query = query.where(filter=FieldFilter("round", "==", round_num))

    docs = query.stream()
    rows = [doc.to_dict() for doc in docs]
    
    logger.info(f"Firestore query returned {len(rows)} rows for branch={branch}, category={category}, gender={gender}, year={year}")
    if rows:
        logger.info(f"Sample row: {rows[0]}")

    # If no results found for specific gender, try fallback to "Any" gender
    if not rows and _gender_specific and gender in ("Boys", "Girls"):
        logger.info(f"No results for {gender}, trying fallback to 'Any' gender")
        fallback_query = db.collection(COLLECTION)
        fallback_query = fallback_query.where(filter=FieldFilter("branch", "==", branch))
        fallback_query = fallback_query.where(filter=FieldFilter("category", "==", category))
        fallback_query = fallback_query.where(filter=FieldFilter("gender", "==", "Any"))
        fallback_query = fallback_query.where(filter=FieldFilter("quota", "==", quota))
        if ph_type:
            fallback_query = fallback_query.where(filter=FieldFilter("ph_type", "==", ph_type))
        if year:
            fallback_query = fallback_query.where(filter=FieldFilter("year", "==", year))
        if round_num:
            fallback_query = fallback_query.where(filter=FieldFilter("round", "==", round_num))
        
        fallback_docs = fallback_query.stream()
        fallback_rows = [doc.to_dict() for doc in fallback_docs]
        if fallback_rows:
            rows.extend(fallback_rows)
            logger.info(f"Fallback query found {len(fallback_rows)} rows with 'Any' gender")

    # Also check with 'caste' field for older EWS records that use that name
    if not rows or category == "EWS":
        alt_query = db.collection(COLLECTION)
        alt_query = alt_query.where(filter=FieldFilter("branch", "==", branch))
        alt_query = alt_query.where(filter=FieldFilter("caste", "==", category))
        if _gender_specific:
            alt_query = alt_query.where(filter=FieldFilter("gender", "==", gender))
        alt_query = alt_query.where(filter=FieldFilter("quota", "==", quota))
        if year:
            alt_query = alt_query.where(filter=FieldFilter("year", "==", year))
        alt_docs = alt_query.stream()
        for doc in alt_docs:
            d = doc.to_dict()
            # Normalize: map old field names to new ones
            if "caste" in d and "category" not in d:
                d["category"] = d["caste"]
            _resolve_rank_fields(d)
            rows.append(d)

    # Normalize first_rank / last_rank / cutoff_rank for every row
    for r in rows:
        _resolve_rank_fields(r)

    # Deduplicate rows — main query + alt_query may return the same Firestore doc
    # (old EWS docs have both 'caste' and 'category' fields after merge-upsert).
    # Keep the row with the most complete data (prefer rows WITH first_rank).
    seen_keys: dict = {}
    for r in rows:
        key = (
            r.get("branch", ""),
            r.get("category", r.get("caste", "")),
            r.get("year", ""),
            r.get("round", ""),
            r.get("gender", ""),
            r.get("quota", ""),
        )
        if key not in seen_keys:
            seen_keys[key] = r
        else:
            # Prefer the row that has first_rank populated
            existing = seen_keys[key]
            if existing.get("first_rank") is None and r.get("first_rank") is not None:
                seen_keys[key] = r
    rows = list(seen_keys.values())

    # Sort: latest year first, then latest round
    rows.sort(key=lambda r: (r.get("year", 0), r.get("round", 0)), reverse=True)

    if not rows:
        return CutoffResult(
            found=False,
            branch=branch,
            category=category,
            year=year,
            round=round_num,
            message=(
                f"Data not found in Firestore for the specified filters: "
                f"**{branch}** / **{category}**"
                + (f" / **{year}**" if year else "")
                + (f" / Round {round_num}" if round_num else "")
                + (f" / **{gender}**" if _gender_specific else "")
                + f" / {quota} quota."
            ),
        )

    dept_url = _get_department_url(branch)
    dept_link = f"\n\nExplore {branch} Department: {dept_url}" if dept_url else ""

    # ── Trend mode: show ALL available years with trend analysis ──
    if not year and show_trend and len(set(r.get("year") for r in rows)) > 1:
        years_seen: dict[int, dict] = {}
        for r in rows:
            y = r.get("year")
            if y and y not in years_seen:
                years_seen[y] = r
        sorted_years = sorted(years_seen.keys())

        year_lines: list[str] = []
        ranks_list: list[int] = []
        for y in sorted_years:
            r = years_seen[y]
            cr = r.get("cutoff_rank")
            lr = r.get("last_rank") if r.get("last_rank") is not None else cr
            fr = r.get("first_rank")   # None when not stored in Firestore

            if lr is None:
                year_lines.append(f"• **{y}**: No allotments recorded (N/A)")
            elif fr is not None and fr != lr:
                year_lines.append(f"• **{y}**: First Rank **{fr:,}** | Last Rank (Cutoff) **{lr:,}**")
            else:
                year_lines.append(f"• **{y}**: Last Rank (Cutoff) **{lr:,}**")
            if cr is not None:
                ranks_list.append(cr)

        trend_analysis = ""
        valid_ranks = [v for v in ranks_list if v > 0]
        if len(valid_ranks) >= 2:
            pct_change = ((valid_ranks[-1] - valid_ranks[0]) / valid_ranks[0] * 100) if valid_ranks[0] > 0 else 0
            if abs(pct_change) < 5:
                trend_analysis = (
                    f"\n\n📊 **Trend Analysis:** The cutoff has remained relatively stable "
                    f"(~{abs(pct_change):.1f}% change). This branch maintains consistent demand."
                )
            elif pct_change < 0:
                trend_analysis = (
                    f"\n\n📊 **Trend Analysis:** Closing rank decreased by **{abs(pct_change):.1f}%** "
                    f"({sorted_years[0]}→{sorted_years[-1]}) — rising competition."
                )
            else:
                trend_analysis = (
                    f"\n\n📊 **Trend Analysis:** Closing rank increased by **{pct_change:.1f}%** "
                    f"({sorted_years[0]}→{sorted_years[-1]}) — improving admission chances."
                )

        message = (
            f"Cutoff ranks for **{branch}** | **{category}** | {quota} quota"
            + (f" | {gender}" if _gender_specific else "")
            + " across all available years:\n\n"
            + "\n".join(year_lines)
            + trend_analysis
            + dept_link
            + "\n\nWARNING: Based on previous year data. Cutoffs may vary."
        )

        best = rows[0]
        return CutoffResult(
            found=True,
            cutoff_rank=best.get("cutoff_rank"),
            first_rank=best.get("first_rank"),
            last_rank=best.get("last_rank", best.get("cutoff_rank")),
            branch=best.get("branch", branch),
            category=best.get("category", category),
            year=best.get("year"),
            round=best.get("round"),
            gender=best.get("gender", gender),
            quota=best.get("quota", quota),
            message=message,
            all_results=rows,
        )

    # ── Standard mode ────────────────────────────────────────────────────
    # Each attribute is on its own separate line (\n → <br> in the widget).
    # No list-marker prefixes — they can collapse inside host-page CSS.
    #
    # Determine target year (latest available if not specified)
    target_year = year if year else max(r.get("year", 0) for r in rows)
    year_rows = [r for r in rows if r.get("year") == target_year]

    # Determine which rounds to show (all rounds sorted ascending, or the
    # specified round only)
    if round_num:
        display_rows = [r for r in year_rows if r.get("round") == round_num]
    else:
        display_rows = year_rows

    # Sort by round ascending, then gender (Boys before Girls)
    display_rows.sort(key=lambda r: (r.get("round", 0), r.get("gender", "")))

    if not display_rows:
        display_rows = rows  # fallback: show whatever we have

    blocks: list[str] = []

    for r in display_rows:
        if _gender_specific and r.get("gender") != gender:
            continue

        fr = r.get("first_rank")   # None when not stored in Firestore
        lr = r.get("last_rank") if r.get("last_rank") is not None else r.get("cutoff_rank")

        fr_str = f"{fr:,}" if fr is not None else "N/A"
        lr_str = f"{lr:,}" if lr is not None else "N/A"

        block = (
            f"**Branch:** {r.get('branch', branch)}\n"
            f"**Category:** {r.get('category', category)}\n"
            f"**Gender:** {r.get('gender', '—')}\n"
            f"**Quota:** {r.get('quota', quota)}\n"
            f"**Round:** {r.get('round', '—')}\n"
            f"**First Rank (Opening):** {fr_str}\n"
            f"**Last Rank (Closing):** {lr_str}"
        )
        blocks.append(block)

    separator = "\n\n" + "─" * 36 + "\n\n"
    header = f"**EAPCET Cutoff Ranks — {target_year}**\n\n"
    message = header + separator.join(blocks) + dept_link + "\n\nWARNING: Based on previous year data. Cutoffs may vary."

    best = display_rows[0]
    return CutoffResult(
        found=True,
        cutoff_rank=best.get("cutoff_rank"),
        first_rank=best.get("first_rank"),
        last_rank=best.get("last_rank") if best.get("last_rank") is not None else best.get("cutoff_rank"),
        branch=best.get("branch", branch),
        category=best.get("category", category),
        year=best.get("year"),
        round=best.get("round"),
        gender=best.get("gender", gender),
        quota=best.get("quota", quota),
        message=message,
        all_results=rows,
    )


def check_eligibility(
    rank: int,
    branch: str,
    category: str,
    year: int | None = None,
    round_num: int | None = None,
    gender: str = "Boys",
) -> CutoffResult:
    """
    Check if a given rank qualifies for a branch + category.
    Uses the latest available year/round if not specified.
    """
    db = get_db()
    if db is None:
        logger.warning("Firestore not available. Cannot check eligibility.")
        return CutoffResult(
            message="WARNING: Cutoff database is currently unavailable. Please try general admission questions instead, or contact admissionsenquiry@vnrvjiet.in for eligibility information.",
            found=False,
        )
    
    result = get_cutoff(branch, category, year, round_num, gender=gender)

    if result.cutoff_rank is None:
        result.eligible = None
        return result

    result.eligible = rank <= result.cutoff_rank

    # Add department URL suggestion
    dept_url = _get_department_url(result.branch)
    dept_link = f"\n\nExplore {result.branch} Department: {dept_url}" if dept_url else ""

    closing = result.cutoff_rank
    opening = result.first_rank
    rank_range = (
        f"First Rank: **{opening:,}** | Last Rank (Cutoff): **{closing:,}**"
        if opening and opening != closing
        else f"Cutoff (Closing) Rank: **{closing:,}**"
    )

    if result.eligible:
        result.message = (
            f"✅ With a rank of **{rank:,}**, you are **eligible** for "
            f"**{result.branch}** under **{result.category}** ({result.gender}) "
            f"— Year {result.year}, Round {result.round}, {result.quota} quota.\n\n"
            f"{rank_range}"
            + dept_link
            + "\n\n⚠️ _Based on previous year data. Actual cutoffs may vary._"
        )
    else:
        result.message = (
            f"❌ With a rank of **{rank:,}**, you are **not eligible** for "
            f"**{result.branch}** under **{result.category}** ({result.gender}) "
            f"— Year {result.year}, Round {result.round}, {result.quota} quota.\n\n"
            f"{rank_range}\n"
            f"Your rank must be <= {closing:,} to qualify."
            + dept_link
            + "\n\n⚠️ _Based on previous year data. Actual cutoffs may vary._"
        )

    return result


def list_branches() -> list[str]:
    """Return all distinct, normalised B.Tech branches in Firestore.

    Raw Firestore values are normalised (e.g. CIVIL → CIV, MECH → ME)
    and deduplicated before being returned.  Non-branch strings such as
    establishment years ("Estd.1995") are excluded via a whitelist of
    known valid branch codes.
    """
    # Canonical set of valid B.Tech branch codes offered at VNRVJIET.
    # Any Firestore value that does NOT normalise to one of these is silently
    # ignored so that garbage values (e.g. "Estd.1995") never reach users.
    VALID_BRANCHES: set[str] = {
        "CSE", "ECE", "EEE", "IT", "ME", "CIV",
        "CSE-CSM",   # AI & ML
        "CSE-CSD",   # Data Science
        "CSE-CSC",   # Cyber Security
        "CSE-CSO",   # IoT
        "CSB",       # CS & Business Systems
        "AID",       # AI & Data Science
        "AUT",       # Automobile Engineering
        "BIO",       # Biotechnology
        "EIE",       # Electronics & Instrumentation
        "RAI",       # Robotics & AI
        "VLSI",      # VLSI Design
    }

    db = get_db()
    if db is None:
        logger.warning("Firestore not available. Returning default branch list.")
        return sorted(VALID_BRANCHES)

    docs = db.collection(COLLECTION).stream()
    normalised: set[str] = set()
    for doc in docs:
        raw = doc.to_dict().get("branch", "")
        if not raw:
            continue
        nb = _normalise_branch(raw)
        if nb in VALID_BRANCHES:
            normalised.add(nb)

    return sorted(normalised)


def list_categories() -> list[str]:
    """Return all distinct categories in Firestore."""
    db = get_db()
    if db is None:
        logger.warning("Firestore not available. Returning default category list.")
        return ["OC", "BC-A", "BC-B", "BC-C", "BC-D", "SC", "ST", "EWS"]
    
    docs = db.collection(COLLECTION).stream()
    cats = sorted({doc.to_dict().get("category", "") for doc in docs})
    return [c for c in cats if c]


def get_all_cutoffs_for_branch(
    branch: str, year: int | None = None
) -> list[dict]:
    """Return every document for a branch (all categories/rounds)."""
    branch = _normalise_branch(branch)
    db = get_db()
    if db is None:
        logger.warning("Firestore not available. Cannot get cutoffs.")
        return []
    
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


def get_cutoffs_flexible(
    branch: str | None = None,
    category: str | None = None,
    gender: str | None = None,
    year: int | None = None,
    round_num: int | None = None,
    quota: str = "Convenor",
    limit: int = 100,
) -> list[dict]:
    """
    Flexible cutoff query that allows filtering by any combination of parameters.
    Use None or omit parameters to get all values for that dimension.
    
    Parameters
    ----------
    branch : str | None – Specific branch code or None for all branches
    category : str | None – Specific category or None for all categories
    gender : str | None – "Boys", "Girls", or None for all genders
    year : int | None – Specific year or None for latest/all years
    round_num : int | None – Specific round or None for all rounds
    quota : str – "Convenor", "SPORTS", etc.
    limit : int – Maximum number of results to return
    
    Returns
    -------
    list[dict] : List of cutoff records matching the criteria
    """
    logger.info(f"get_cutoffs_flexible called: branch={branch}, category={category}, gender={gender}, year={year}")
    
    # Normalize inputs if provided
    if branch:
        branch = _normalise_branch(branch)
    if category:
        category = _normalise_category(category)
    
    db = get_db()
    if db is None:
        logger.warning("Firestore not available. Cannot query cutoff data.")
        return []

    query = db.collection(COLLECTION)

    # Apply filters only for non-None parameters
    if branch:
        query = query.where(filter=FieldFilter("branch", "==", branch))
    if category:
        query = query.where(filter=FieldFilter("category", "==", category))
    if gender:
        query = query.where(filter=FieldFilter("gender", "==", gender))
    if quota:
        query = query.where(filter=FieldFilter("quota", "==", quota))
    if year:
        query = query.where(filter=FieldFilter("year", "==", year))
    if round_num:
        query = query.where(filter=FieldFilter("round", "==", round_num))

    # Fetch documents
    docs = query.limit(limit).stream()
    rows = [doc.to_dict() for doc in docs]
    
    logger.info(f"get_cutoffs_flexible returned {len(rows)} rows")
    
    # Handle old 'caste' field for EWS records
    if category == "EWS" or not category:
        alt_query = db.collection(COLLECTION)
        if branch:
            alt_query = alt_query.where(filter=FieldFilter("branch", "==", branch))
        if category:
            alt_query = alt_query.where(filter=FieldFilter("caste", "==", category))
        if gender:
            alt_query = alt_query.where(filter=FieldFilter("gender", "==", gender))
        if quota:
            alt_query = alt_query.where(filter=FieldFilter("quota", "==", quota))
        if year:
            alt_query = alt_query.where(filter=FieldFilter("year", "==", year))
        
        alt_docs = alt_query.limit(limit).stream()
        for doc in alt_docs:
            d = doc.to_dict()
            # Normalize old field names
            if "caste" in d and "category" not in d:
                d["category"] = d["caste"]
            if "cutoff_rank" not in d:
                d["cutoff_rank"] = d.get("last_rank") or d.get("first_rank")
            if d.get("cutoff_rank") is not None and d not in rows:
                rows.append(d)
    
    # Sort by year (desc), branch, category, round (desc)
    rows.sort(
        key=lambda r: (
            r.get("year", 0),
            r.get("branch", ""),
            r.get("category", ""),
            r.get("round", 0)
        ),
        reverse=True,
    )
    
    return rows


def format_cutoffs_table(
    cutoffs: list[dict],
    title: str = "Cutoff Ranks",
    max_rows: int = 50,
) -> str:
    """
    Format a list of cutoff records into a readable table/message.
    
    Parameters
    ----------
    cutoffs : list[dict] – Cutoff records from get_cutoffs_flexible
    title : str – Title for the table
    max_rows : int – Maximum rows to display
    
    Returns
    -------
    str : Formatted message with cutoff data
    """
    if not cutoffs:
        return "Data not found in Firestore for the specified filters."

    # Normalise rank fields on every row (idempotent)
    for row in cutoffs:
        _resolve_rank_fields(row)

    # Group by branch for better readability
    by_branch: dict[str, list[dict]] = {}
    for row in cutoffs[:max_rows]:
        branch = row.get("branch", "Unknown")
        if branch not in by_branch:
            by_branch[branch] = []
        by_branch[branch].append(row)

    blocks: list[str] = []

    for branch_name, records in by_branch.items():
        # Group by year within branch
        by_year: dict = {}
        for rec in records:
            y = rec.get("year", "N/A")
            if y not in by_year:
                by_year[y] = []
            by_year[y].append(rec)

        for year_key in sorted(by_year.keys(), reverse=True):
            year_records = by_year[year_key]

            for rec in sorted(year_records, key=lambda r: (r.get("round", 0), r.get("gender", ""))):
                cat = rec.get("category", "—")
                gen = rec.get("gender", "—")
                rnd = rec.get("round", "—")
                qt  = rec.get("quota", "Convenor")
                fr  = rec.get("first_rank")
                lr  = rec.get("last_rank") if rec.get("last_rank") is not None else rec.get("cutoff_rank")

                fr_str = f"{fr:,}" if isinstance(fr, int) else "N/A"
                lr_str = f"{lr:,}" if isinstance(lr, int) else "N/A"

                block = (
                    f"**Branch:** {branch_name}\n"
                    f"**Category:** {cat}\n"
                    f"**Gender:** {gen}\n"
                    f"**Quota:** {qt}\n"
                    f"**Round:** {rnd}\n"
                    f"**Year:** {year_key}\n"
                    f"**First Rank (Opening):** {fr_str}\n"
                    f"**Last Rank (Closing):** {lr_str}"
                )
                blocks.append(block)

    separator = "\n\n" + "─" * 36 + "\n\n"
    output = f"**{title}**\n\n" + separator.join(blocks[:max_rows])

    if len(cutoffs) > max_rows:
        output += f"\n\n_Showing first {max_rows} of {len(cutoffs)} results._"

    output += "\n\nWARNING: Based on previous year data. Cutoffs may vary."
    return output
