"""
Input validators and sanitisers.
"""

from __future__ import annotations

import html
import re


def sanitise_input(text: str) -> str:
    """
    Clean user input before processing.
    - Strip leading/trailing whitespace
    - Escape HTML entities (XSS prevention)
    - Collapse multiple spaces
    - Limit length to 1000 chars
    """
    text = text.strip()
    text = html.escape(text, quote=True)
    text = re.sub(r"\s+", " ", text)
    return text[:1000]


def extract_rank(text: str) -> int | None:
    """
    Try to extract a numeric rank from the user query.
    Valid EAPCET rank range: 1 to 200000.
    Handles "21000", "21k", "rank 21000", etc.
    """
    # "21k" → 21000
    k_match = re.search(r"(\d+)\s*k\b", text, re.I)
    if k_match:
        val = int(k_match.group(1)) * 1000
        if 1 <= val <= 200000:
            return val
        return None

    # Plain number like "2022" or "15000"
    num_match = re.search(r"\b(\d+)\b", text)
    if num_match:
        val = int(num_match.group(1))
        if 1 <= val <= 200000:
            return val
        return None

    return None


# ── Shared branch patterns (maps to Firestore branch codes) ──
_BRANCH_PATTERNS = {
    r"\b(?:cse|computer\s*science)\b": "CSE",
    r"\b(?:ece|electronics)\b": "ECE",
    r"\b(?:eee|electrical)\b": "EEE",
    r"\b(?:it|information\s*technology)\b": "IT",
    r"\b(?:mech|mechanical|me)\b": "ME",
    r"\b(?:civil|civ)\b": "CIV",
    r"\b(?:ai\s*(?:&|and)?\s*ml|aiml|artificial\s*intelligence)\b": "CSE-CSM",
    r"\b(?:ai\s*(?:&|and)?\s*ds|aids|ai\s*(?:&|and)?\s*data\s*science)\b": "AID",
    r"\baid\b": "AID",
    r"\b(?:data\s*science|csd)\b": "CSE-CSD",
    r"\b(?:csm|machine\s*learning)\b": "CSE-CSM",
    r"\b(?:csc|cyber\s*security)\b": "CSE-CSC",
    r"\b(?:cso|iot|internet\s*of\s*things)\b": "CSE-CSO",
    r"\b(?:csb|business\s*systems|cs\s*business)\b": "CSB",
    r"\b(?:aut|automobile)\b": "AUT",
    r"\b(?:bio|biotech|biotechnology)\b": "BIO",
    r"\beie\b": "EIE",
    r"\b(?:rai|robotics)\b": "RAI",
    r"\bvlsi\b": "VLSI",
}


def extract_branch(text: str) -> str | None:
    """Attempt to extract a branch name from user text."""
    for pattern, branch in _BRANCH_PATTERNS.items():
        if re.search(pattern, text, re.I):
            return branch
    return None


def extract_branches(text: str) -> list[str]:
    """
    Extract one or more branch names from user text.
    Supports:
      - "all" / "all branches" / "every branch" → returns ["ALL"]
      - Comma / "and" separated: "CSE, ECE and IT" → ["CSE", "ECE", "IT"]
      - Single branch: "CSE" → ["CSE"]
    Returns empty list if nothing detected.
    """
    t = text.strip().lower()

    # Check for "all branches"
    if re.search(r"\b(?:all|every|each)\b", t):
        return ["ALL"]

    found = []
    for pattern, branch in _BRANCH_PATTERNS.items():
        if re.search(pattern, text, re.I) and branch not in found:
            found.append(branch)

    return found


def extract_category(text: str) -> str | None:
    """Attempt to extract a reservation category from user text."""
    cat_patterns = {
        r"\boc\b|\bopen\s*category\b|\bgeneral\s*category\b|\bgeneral\b": "OC",
        r"\bobc\b|\bbc[\s-]?d\b": "BC-D",
        r"\bbc[\s-]?a\b": "BC-A",
        r"\bbc[\s-]?b\b": "BC-B",
        r"\bbc[\s-]?c\b": "BC-C",
        r"\bbc[\s-]?e\b": "BC-E",
        r"\bsc[\s-]?iii\b|\bsc[\s-]?3\b": "SC-III",
        r"\bsc[\s-]?ii\b|\bsc[\s-]?2\b": "SC-II",
        r"\bsc[\s-]?i\b|\bsc[\s-]?1\b": "SC-I",
        r"\bsc\b": "SC",
        r"\bst\b": "ST",
        r"\bews\b": "EWS",
    }
    for pattern, category in cat_patterns.items():
        if re.search(pattern, text, re.I):
            return category
    return None


def extract_gender(text: str) -> str | None:
    """Extract gender from user text. Returns 'Boys' or 'Girls' or None."""
    t = text.lower()
    if re.search(r"\b(girl|girls|female|women|woman|daughter)\b", t):
        return "Girls"
    if re.search(r"\b(boy|boys|male|men|man|son)\b", t):
        return "Boys"
    return None


def extract_quota(text: str) -> str | None:
    """Extract special quota type from user text."""
    t = text.lower()
    if re.search(r"\bsport", t):
        return "SPORTS"
    if re.search(r"\bcap\b", t):
        return "CAP"
    if re.search(r"\bncc\b", t):
        return "NCC"
    if re.search(r"\bothers?\s*(?:quota|category|ph|handicap|disab)", t):
        return "OTHERS"
    if re.search(r"\b(?:ph[ovhma]|physically\s*handicap|disabilit|pwd)\b", t):
        return "OTHERS"
    return None


def extract_year(text: str) -> int | None:
    """Extract a 4-digit year between 2019-2030."""
    m = re.search(r"\b(20[1-3]\d)\b", text)
    return int(m.group(1)) if m else None
