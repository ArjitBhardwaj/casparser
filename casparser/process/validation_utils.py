"""Utilities for validating data from CAS statements."""

import re


def is_valid_fund_name(name: str) -> bool:
    """
    Check if a fund name is valid (not corrupted/incomplete).
    Returns True if the name appears to be a valid fund name.
    """
    if not name or not isinstance(name, str):
        return False

    name = name.strip()

    # Empty or very short names are invalid
    if len(name) < 3:
        return False

    # Names that are just numbers or mostly numbers are invalid
    if re.match(r'^[\d\s,.]+$', name):
        return False

    # Names that look like UCC codes, folio numbers, or technical identifiers
    ucc_patterns = [
        r'^MF[A-Z0-9]+$',  # MFBRLA0028, MFPRUI0072, etc.
        r'^[A-Z]{2,6}\d{4,}$',  # Technical codes like MFPRUI0058
        r'^\d{6,}$',  # Pure folio numbers like 149091
        r'^[A-Z]{1,3}$',  # Very short codes like "M", "NOT"
        r'^NOT\s+AVAILABLE$',  # "NOT AVAILABLE"
        r'^AVAILABLE$',  # Partial "NOT AVAILABLE"
    ]

    for pattern in ucc_patterns:
        if re.match(pattern, name.upper()):
            return False

    # Names that are mostly data patterns (multiple sequences of numbers/commas)
    if re.search(r'[\d,.]+ [\d,.]+ [\d,.]+ [\d,.]+', name):
        return False

    # Names that contain excessive numeric data
    numeric_ratio = len(re.findall(r'[\d,.]', name)) / len(name)
    if numeric_ratio > 0.5:  # If more than 50% is numbers/punctuation
        return False

    # Check for minimum word content
    words = re.findall(r'[A-Za-z]+', name)
    if len(words) < 2 and len(name) < 10:  # Very short with < 2 words
        return False

    # Names that are just common suffixes without company name
    suffix_only_patterns = [
        r'^(LIMITED|LTD|CORPORATION|CORP|FUND|MUTUAL)$',
        r'^(INDIA|PRIVATE|PVT|PUBLIC)$',
        r'^(SERVICES?|TECHNOLOGIES?|INDUSTRIES?)$',
    ]

    for pattern in suffix_only_patterns:
        if re.match(pattern, name.upper()):
            return False

    return True


def enhanced_looks_like_corporate_bond(name: str) -> bool:
    """
    Enhanced heuristic to classify bond/NCD/NCB/debenture by name tokens.
    More comprehensive detection of corporate bonds.
    """
    if not name:
        return False

    # Normalize the name for pattern matching
    norm = re.sub(r"[^A-Z0-9\s]+", " ", name.upper()).strip()

    # Primary bond indicators - strong signals
    primary_indicators = [
        r'\bBOND\b', r'\bBONDS\b', r'\bDEBENTURE\b', r'\bDEBENTURES\b',
        r'\bNCD\b', r'\bNCB\b', r'\bFIXED\s+INTEREST\b',
        r'\bTAX\s*-?\s*FREE\b', r'\bTAX\s+FREE\b'
    ]

    # Secondary indicators - supportive but not definitive alone
    secondary_indicators = [
        r'\bCORPORATION\b', r'\bDEVELOPMENT\b', r'\bFINANCE\b',
        r'\bHOUSING\b', r'\bURBAN\b', r'\bINDUSTRIES\b',
        r'\b\d+\.\d+%?\b',  # Interest rates like 8.10, 8.00%
        r'\b\d{2}-[A-Z]{3}\b',  # Date patterns like 05-Mar, 23-Feb
        r'\bONCE\s+A\s+YEAR\b'
    ]

    # Check for primary indicators
    primary_matches = sum(1 for pattern in primary_indicators if re.search(pattern, norm))

    # Check for secondary indicators
    secondary_matches = sum(1 for pattern in secondary_indicators if re.search(pattern, norm))

    # Decision logic:
    # - If we have any primary indicator, it's likely a bond
    # - If we have multiple (3+) secondary indicators, it's likely a bond
    # - Special case: if it contains both CORPORATION and DEVELOPMENT and numbers, likely a bond
    if primary_matches > 0:
        return True

    if secondary_matches >= 3:
        return True

    # Special case for development corporations with numerical patterns
    if (re.search(r'\bCORPORATION\b', norm) and
            re.search(r'\bDEVELOPMENT\b', norm) and
            re.search(r'\b\d+\.\d+\b', norm)):
        return True

    # Check for specific corporate bond naming patterns
    corp_bond_patterns = [
        r'LIMITED\s+FIXED\s+INTEREST',
        r'CORPORATION\s+LIMITED\s+FIXED',
        r'DEVELOPMENT\s+CORPORATION\s+LIMITED'
    ]

    for pattern in corp_bond_patterns:
        if re.search(pattern, norm):
            return True

    return False


def looks_like_corporate_bond(name: str) -> bool:
    """Wrapper function to maintain backward compatibility."""
    return enhanced_looks_like_corporate_bond(name)