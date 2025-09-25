"""Utilities for cleaning and normalizing names from CAS statements."""

import re


def clean_equity_name(name: str) -> str:
    """Clean equity name by removing text before first \t\t and all \t\t sequences."""
    if not name:
        return name

    # Find the first occurrence of \t\t
    if '\t\t' in name:
        # Split by first \t\t and take everything after it
        first_tab_index = name.find('\t\t')
        company_name_part = name[first_tab_index + 2:]  # +2 to skip the \t\t

        # Remove any remaining \t\t sequences and replace with spaces
        clean_name = company_name_part.replace('\t\t', ' ').strip()

        # Clean up multiple spaces
        clean_name = ' '.join(clean_name.split())

        return clean_name

    # If no \t\t found, return the original name stripped
    return name.strip()


def clean_corporate_bond_name(name: str) -> str:
    """Clean corporate bond name by preserving the full name and replacing \t and \n with spaces."""
    if not name:
        return name

    # Go through the name character by character and replace \t and \n with spaces
    cleaned_chars = []
    for char in name:
        if char == '\t' or char == '\n':
            cleaned_chars.append(' ')
        else:
            cleaned_chars.append(char)

    clean_name = ''.join(cleaned_chars)

    # Clean up multiple spaces
    clean_name = ' '.join(clean_name.split())

    # Remove everything after "once" (case-insensitive) as it's usually descriptive text
    # like "Once a year 8.10 05-Mar"
    once_index = clean_name.lower().find(' once')
    if once_index != -1:
        clean_name = clean_name[:once_index]

    # Remove leading/trailing whitespace
    clean_name = clean_name.strip()

    return clean_name


def clean_fund_name(name: str) -> str:
    """Clean fund name by removing embedded data."""
    if not name:
        return name

    # Remove patterns like "85,649.842 85,649.842 0.000 0.000 0.000 0.000 0.000 0.000"
    name = re.sub(r'\s+[\d,.]+ [\d,.]+ [\d,.]+ [\d,.]+ [\d,.]+ [\d,.]+ [\d,.]+ [\d,.]+', '', name)

    # Remove patterns like "149091 UTI Focused Fund - Direct Plan 599339423935 49,997.50 0 10.0000 4,99,975.00"
    name = re.sub(r'^[\w\d]+\s+(.+?)\s+[\d,.]+ [\d,.]+ [\d,.]+ [\d,.]+ [\d,.]+$', r'\1', name)

    # Remove standalone folio numbers at the beginning or end
    name = re.sub(r'^\d{8,15}\s+', '', name)  # Remove folio at start
    name = re.sub(r'\s+\d{8,15}$', '', name)  # Remove folio at end

    # Remove trailing numbers and spaces
    name = re.sub(r'\s+[\d,.]+\s*$', '', name)

    # Remove common data patterns that might be embedded
    name = re.sub(r'\s+\d+\.\d+\s+\d+\.\d+\s+[\d,]+\.?\d*', '', name)

    # Remove UCC patterns that might be embedded
    name = re.sub(r'\s+(NOT AVAILABLE|MFAXIS\d+|MF/\d+/\d+/\d+/\d+|MFPRUI\d+)\s*', ' ', name)

    # Clean up extra whitespace
    name = re.sub(r'\s+', ' ', name).strip()

    # Remove leading/trailing punctuation that might be artifacts
    name = re.sub(r'^[^\w]+|[^\w]+$', '', name)

    return name