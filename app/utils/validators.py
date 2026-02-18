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
# Order matters: More specific patterns should come first to avoid false matches
_BRANCH_PATTERNS = {
    # CSE variants with specializations (check these first before generic CSE)
    r"\b(?:cse[\s\-]*(?:ai|artificial\s+intelligence)[\s\-&]*(?:ml|machine\s+learning)|ai[\s\-&]*ml|aiml|artificial\s+intelligence\s+(?:and\s+)?machine\s+learning|cse[\s\-]*csm)\b": "CSE-CSM",
    r"\b(?:cse[\s\-]*(?:ai|artificial\s+intelligence)[\s\-&]*(?:ds|data\s+science)|ai[\s\-&]*ds|artificial\s+intelligence\s+(?:and\s+)?data\s+science)\b": "AID",
    r"\baid(?:s)?\b": "AID",  # Standalone AID/AIDS
    r"\b(?:cse[\s\-]*(?:data\s+science|ds)|csd|cse[\s\-]*csd)\b": "CSE-CSD",
    r"\bdata\s+science\b": "CSE-CSD",  # Standalone data science (after checking AI+DS combo)
    r"\b(?:cse[\s\-]*(?:cyber\s+security|cys)|cyber\s+security|cybersecurity|csc|cse[\s\-]*csc)\b": "CSE-CSC",
    r"\b(?:cse[\s\-]*(?:iot|internet\s+of\s+things)|internet\s+of\s+things|cso|cse[\s\-]*cso)\b": "CSE-CSO",
    r"\biot\b": "CSE-CSO",  # Standalone IoT
    r"\b(?:cse[\s\-]*(?:business\s+systems?|bs)|computer\s+science[\s\-&]*business\s+systems?|cs\s+business|csb)\b": "CSB",
    r"\bcsm\b": "CSE-CSM",  # Standalone CSM
    
    # Generic CSE (after checking all specialized variants)
    r"\b(?:cse|computer\s+science(?:\s+(?:and|&)\s+engineering)?|computer\s+engineering)\b": "CSE",
    r"\bcs\b": "CSE",  # Standalone CS
    
    # EEE/Electrical (check before ECE to handle "electrical and electronics" correctly)
    r"\b(?:eee|electrical\s+and\s+electronics(?:\s+engineering)?|electrical\s+engineering)\b": "EEE",
    r"\belectrical\b": "EEE",
    r"\bee\b": "EEE",
    
    # ECE/Electronics
    r"\b(?:ece|electronics\s+(?:and|&)\s+communication(?:\s+engineering)?|electronics\s+communication)\b": "ECE",
    r"\belectronics\b": "ECE",
    r"\bec\b": "ECE",
    
    # IT
    r"\b(?:information\s+technology|it)\b": "IT",
    
    # Mechanical
    r"\b(?:mechanical(?:\s+engineering)?|mech)\b": "ME",
    r"\bme\b": "ME",
    
    # Civil
    r"\b(?:civil(?:\s+engineering)?|civ)\b": "CIV",
    r"\bce\b": "CIV",
    
    # Other specialized branches
    r"\b(?:robotics(?:\s+(?:and|&)\s+(?:ai|artificial\s+intelligence))?|rai)\b": "RAI",
    r"\bvlsi\b": "VLSI",
    r"\b(?:automobile(?:\s+engineering)?|aut)\b": "AUT",
    r"\b(?:biotechnology|biotech|bio)\b": "BIO",
    r"\b(?:electronics\s+(?:and|&)\s+instrumentation(?:\s+engineering)?|instrumentation|eie)\b": "EIE",
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
