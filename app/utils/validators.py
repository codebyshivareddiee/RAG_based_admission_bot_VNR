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
    Handles "21,000", "21000", "21k", "rank 21000", etc.
    """
    # "21k" → 21000
    k_match = re.search(r"(\d+)\s*k\b", text, re.I)
    if k_match:
        return int(k_match.group(1)) * 1000

    # "21,000" or "21000"
    num_match = re.search(r"(\d{1,3}(?:,\d{3})*|\d+)", text)
    if num_match:
        return int(num_match.group(1).replace(",", ""))

    return None


def extract_branch(text: str) -> str | None:
    """Attempt to extract a branch name from user text."""
    branch_patterns = {
        r"\b(?:cse|computer\s*science)\b": "CSE",
        r"\b(?:ece|electronics)\b": "ECE",
        r"\b(?:eee|electrical)\b": "EEE",
        r"\b(?:it|information\s*technology)\b": "IT",
        r"\b(?:mech|mechanical)\b": "MECH",
        r"\b(?:civil)\b": "CIVIL",
        r"\b(?:ai\s*(?:&|and)?\s*ml|aiml|artificial\s*intelligence)\b": "CSE (AI & ML)",
        r"\b(?:data\s*science|ds|csd)\b": "CSE (Data Science)",
    }
    for pattern, branch in branch_patterns.items():
        if re.search(pattern, text, re.I):
            return branch
    return None


def extract_category(text: str) -> str | None:
    """Attempt to extract a reservation category from user text."""
    cat_patterns = {
        r"\boc\b|\bopen\b|\bgeneral\b": "OC",
        r"\bobc\b|\bbc[\s-]?d\b": "BC-D",
        r"\bbc[\s-]?a\b": "BC-A",
        r"\bbc[\s-]?b\b": "BC-B",
        r"\bbc[\s-]?e\b": "BC-E",
        r"\b(?:sc)\b": "SC",
        r"\b(?:st)\b": "ST",
        r"\bews\b": "EWS",
    }
    for pattern, category in cat_patterns.items():
        if re.search(pattern, text, re.I):
            return category
    return None


def extract_year(text: str) -> int | None:
    """Extract a 4-digit year between 2019-2030."""
    m = re.search(r"\b(20[1-3]\d)\b", text)
    return int(m.group(1)) if m else None
