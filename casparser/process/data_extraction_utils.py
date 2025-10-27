"""Utilities for extracting data from CAS statements."""

import re

from .name_cleaning_utils import clean_fund_name
from .regex import (
    CDSL_ACCOUNT_RE,
    NSDL_ACCOUNT_RE,
    NSDL_ISIN_RE,
    get_simple_mf_pattern,
)


def find_account_context(lines, mf_section_line):
    """Find which account the MF section belongs to by looking backwards."""
    # Look backwards from the MF section to find the most recent account header
    for i in range(mf_section_line - 1, -1, -1):
        line = lines[i].strip()

        # Check for CDSL/NSDL account patterns
        cdsl_match = re.search(CDSL_ACCOUNT_RE, line, re.I)
        if cdsl_match:
            return ('CDSL', cdsl_match.groups()[1].strip(), cdsl_match.groups()[2], cdsl_match.groups()[3])

        nsdl_match = re.search(NSDL_ACCOUNT_RE, line, re.I)
        if nsdl_match:
            return ('NSDL', nsdl_match.groups()[1].strip(), nsdl_match.groups()[2], nsdl_match.groups()[3])

    return None


def extract_mf_holdings_data(lines, start_idx):
    """Extract MF holdings data with improved parsing that handles optional fields."""
    holdings = []

    # Track which lines we've processed to avoid duplicates
    processed_lines = set()

    i = start_idx
    while i < len(lines):
        line = lines[i].strip()
        if not line or i in processed_lines:
            i += 1
            continue

        # Stop if we hit another account section
        if re.search(r'(CDSL|NSDL)\s+demat\s+account', line, re.I):
            break

        # Skip non-data lines
        if any(skip_word in line.upper() for skip_word in
               ['ACCOUNT', 'HOLDER', 'CLIENT', 'TOTAL', 'SUBTOTAL', 'GRAND', 'SUB TOTAL']):
            i += 1
            continue

        # Look for ISIN pattern
        isin_match = re.search(NSDL_ISIN_RE, line)
        if not isin_match:
            i += 1
            continue

        isin = isin_match.group()
        processed_lines.add(i)

        # Look ahead to gather all related lines
        full_text = line
        lines_consumed = 1

        for j in range(i + 1, min(i + 8, len(lines))):
            next_line = lines[j].strip()
            if not next_line:
                continue
            # Stop if we hit another ISIN
            if re.search(NSDL_ISIN_RE, next_line):
                break
            # Stop if we hit another account section
            if re.search(r'(CDSL|NSDL)\s+demat\s+account', next_line, re.I):
                break
            full_text += " " + next_line
            lines_consumed += 1

        # Mark consumed lines as processed
        for j in range(i, i + lines_consumed):
            if j < len(lines):
                processed_lines.add(j)

        # Define both patterns upfront
        detailed_pattern_with_extra = (
            rf'({NSDL_ISIN_RE})'  # ISIN
            rf'\s+([A-Z0-9/\s]*?)'  # UCC (can be "NOT AVAILABLE")
            rf'\s+(.+?)'  # Fund name
            rf'\s+(\d+(?:\.\d+)?)'  # Folio number
            rf'\s+([\d,]+(?:\.\d+)?)'  # Balance (units)
            rf'\s+[\d,]+(?:\.\d+)?'  # SKIP: Extra field (internal reference number)
            rf'\s+([\d,]+(?:\.\d+)?)'  # Average cost
            rf'\s+([\d,]+(?:\.\d+)?)'  # Total cost
            rf'\s+([\d,]+(?:\.\d+)?)'  # Current NAV
            rf'\s+([\d,]+(?:\.\d+)?)'  # Current value
            rf'\s+([(-]*[\d,]+(?:\.\d+)?)\)*'  # P&L (can be negative)
            rf'(?:\s+([(-]*[\d,]+(?:\.\d+)?)?\)*)?'  # Returns (optional, can be negative)
        )

        detailed_pattern_without_extra = (
            rf'({NSDL_ISIN_RE})'  # ISIN
            rf'\s+([A-Z0-9/\s]*?)'  # UCC (can be "NOT AVAILABLE")
            rf'\s+(.+?)'  # Fund name
            rf'\s+(\d+(?:\.\d+)?)'  # Folio number
            rf'\s+([\d,]+(?:\.\d+)?)'  # Balance (units)
            rf'\s+([\d,]+(?:\.\d+)?)'  # Average cost
            rf'\s+([\d,]+(?:\.\d+)?)'  # Total cost
            rf'\s+([\d,]+(?:\.\d+)?)'  # Current NAV
            rf'\s+([\d,]+(?:\.\d+)?)'  # Current value
            rf'\s+([(-]*[\d,]+(?:\.\d+)?)\)*'  # P&L (can be negative)
            rf'(?:\s+([(-]*[\d,]+(?:\.\d+)?)?\)*)?'  # Returns (optional, can be negative)
        )

        # Try to parse with flexible field matching
        detailed_match = None
        groups = None

        # First, try the newer format with the extra field (2025+)
        detailed_match_with_extra = re.search(detailed_pattern_with_extra, full_text, re.DOTALL | re.I)

        # If the first pattern fails, try the older format without the extra field
        if not detailed_match_with_extra:
            detailed_match = re.search(detailed_pattern_without_extra, full_text, re.DOTALL | re.I)
            if detailed_match:
                groups = detailed_match.groups()
                if len(groups) >= 10:
                    isin, raw_ucc, raw_name, folio, balance, avg_cost, total_cost, nav, value, pnl = groups[:10]
                    returns = groups[10] if len(groups) > 10 else ""
        else:
            # Use the match with extra field
            detailed_match = detailed_match_with_extra
            groups = detailed_match.groups()
            if len(groups) >= 9:
                isin, raw_ucc, raw_name, folio, balance, avg_cost, total_cost, nav, value = groups[:9]
                pnl = groups[9] if len(groups) > 9 else ""
                returns = groups[10] if len(groups) > 10 else ""

        # Additional validation: Check if the parsed values make sense
        if detailed_match and groups:
            # Clean the name and ucc fields
            name = clean_fund_name(raw_name)
            ucc = (raw_ucc or "").strip()

            # Handle "NOT AVAILABLE" case properly
            if "NOT AVAILABLE" in ucc:
                ucc = "NOT AVAILABLE"
            elif ucc == "NOT" and name.startswith("AVAILABLE"):
                ucc = "NOT AVAILABLE"
                name = name.replace("AVAILABLE", "").strip()
            elif not ucc and "NOT AVAILABLE" in name:
                if name.startswith("NOT AVAILABLE"):
                    ucc = "NOT AVAILABLE"
                    name = name.replace("NOT AVAILABLE", "").strip()

            # Clean up the name
            name = re.sub(r'^\s+', '', name)

            # Skip if this looks like a summary line (corrupted data)
            if re.search(r'[\d,.]+ [\d,.]+ [\d,.]+ [\d,.]+ [\d,.]+ [\d,.]+ [\d,.]+ [\d,.]+', name):
                i += lines_consumed
                continue

            # Additional validation: Check if NAV and value make sense
            try:
                balance_val = float(balance.replace(",", ""))
                nav_val = float(nav.replace(",", "")) if nav else 0
                value_val = float(value.replace(",", "")) if value else 0

                # Basic sanity check: if balance * nav is roughly equal to value
                if balance_val > 0 and nav_val > 0 and value_val > 0:
                    calculated_value = balance_val * nav_val
                    # Allow for some variance due to rounding
                    if abs(calculated_value - value_val) / value_val > 0.1:  # More than 10% difference
                        # This might indicate wrong field mapping, try the other pattern
                        if detailed_match == detailed_match_with_extra:
                            # Try without extra field
                            detailed_match_alt = re.search(detailed_pattern_without_extra, full_text, re.DOTALL | re.I)
                            if detailed_match_alt:
                                groups_alt = detailed_match_alt.groups()
                                if len(groups_alt) >= 10:
                                    # Re-assign with the alternative pattern
                                    isin, raw_ucc, raw_name, folio, balance, avg_cost, total_cost, nav, value, pnl = groups_alt[
                                                                                                                     :10]
                                    returns = groups_alt[10] if len(groups_alt) > 10 else ""

                                    # Revalidate
                                    balance_val_alt = float(balance.replace(",", ""))
                                    nav_val_alt = float(nav.replace(",", "")) if nav else 0
                                    value_val_alt = float(value.replace(",", "")) if value else 0
                                    calculated_value_alt = balance_val_alt * nav_val_alt

                                    if nav_val_alt > 0 and value_val_alt > 0 and abs(
                                            calculated_value_alt - value_val_alt) / value_val_alt <= 0.1:
                                        # This pattern works better, use it
                                        name = clean_fund_name(raw_name)
                                        ucc = (raw_ucc or "").strip()

                                        if "NOT AVAILABLE" in ucc:
                                            ucc = "NOT AVAILABLE"
                                        elif ucc == "NOT" and name.startswith("AVAILABLE"):
                                            ucc = "NOT AVAILABLE"
                                            name = name.replace("AVAILABLE", "").strip()
                                        elif not ucc and "NOT AVAILABLE" in name:
                                            if name.startswith("NOT AVAILABLE"):
                                                ucc = "NOT AVAILABLE"
                                                name = name.replace("NOT AVAILABLE", "").strip()

                                        name = re.sub(r'^\s+', '', name)

                # Skip if balance is 0 or negative
                if balance_val <= 0:
                    i += lines_consumed
                    continue

            except (ValueError, AttributeError):
                i += lines_consumed
                continue

            record = {
                "name": name,
                "isin": isin,
                "ucc": ucc if ucc else "NOT AVAILABLE",
                "folio": (folio or "").strip(),
                "balance": balance.replace(",", "") if balance else "",
                "avg_cost": avg_cost.replace(",", "") if avg_cost else "",
                "total_cost": total_cost.replace(",", "") if total_cost else "",
                "nav": nav.replace(",", "") if nav else "",
                "value": value.replace(",", "") if value else "",
                "pnl": pnl.replace(",", "") if pnl else "",
                "return": returns.replace(",", "") if returns else "",
            }
            holdings.append(record)
            i += lines_consumed
            continue

        # Pattern 2: Simple record (like from mutual_funds section)
        simple_pattern = get_simple_mf_pattern()
        simple_match = re.search(simple_pattern, full_text, re.I)

        if simple_match:
            isin, raw_name, balance, nav, value = simple_match.groups()
            name = clean_fund_name(raw_name)

            # Skip if this looks like corrupted data
            if re.search(r'[\d,.]+ [\d,.]+ [\d,.]+ [\d,.]+ [\d,.]+ [\d,.]+ [\d,.]+ [\d,.]+', name):
                i += lines_consumed
                continue

            record = {
                "name": name,
                "isin": isin,
                "ucc": "",
                "folio": "",
                "balance": balance.replace(",", "") if balance else "",
                "avg_cost": "",
                "total_cost": "",
                "nav": nav.replace(",", "") if nav else "",
                "value": value.replace(",", "") if value else "",
                "pnl": "",
                "return": "",
            }
            holdings.append(record)

        i += lines_consumed

    return holdings