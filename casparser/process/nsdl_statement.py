import re

from casparser_isin import ISINDb

from casparser.exceptions import HeaderParseError
from casparser.types import NSDLCASData, StatementPeriod

from .regex import (
    DEMAT_AC_HOLDER_RE,
    DEMAT_AC_TYPE_RE,
    DEMAT_DP_ID_RE,
    DEMAT_HEADER_RE,
    DEMAT_MF_HEADER_RE,
    DEMAT_MF_TYPE_RE,
    DEMAT_STATEMENT_PERIOD_RE,
    NSDL_CDSL_HOLDINGS_RE,
    NSDL_EQ_RE,
    NSDL_MF_HOLDINGS_RE,
    NSDL_MF_RE,
    BOND_NAME_RE,
)


# --- small helper ---
def looks_like_corporate_bond(name: str) -> bool:
    """Heuristic: classify bond/NCD/NCB/debenture by name tokens."""
    if not name:
        return False
    # Normalize: uppercase, collapse punctuation to spaces so hyphenated tokens match
    norm = re.sub(r"[^A-Z0-9]+", " ", name.upper()).strip()
    return re.search(BOND_NAME_RE, norm, flags=re.I) is not None


def parse_header(text):
    """
    Parse CAS header data.
    :param text: CAS text
    """
    if m := re.search(
            DEMAT_STATEMENT_PERIOD_RE,
            text,
            re.DOTALL | re.MULTILINE | re.I,
    ):
        return m.groupdict()
    raise HeaderParseError("Error parsing CAS header")


def detect_mf_folio_section(lines, start_idx=0):
    """
    Detect MF folio section with multiple pattern variations.
    Returns (found, start_line_idx) tuple.
    """
    mf_section_patterns = [
        r"^Mutual\s+Fund\s+Folios?\s*\(F\)\s*$",
        r"^Mutual\s+Fund\s+Folios?\s*$",
        r"^MF\s+Folios?\s*\(F\)\s*$",
        r"^MF\s+Folios?\s*$",
        r"^Folios?\s*\(F\)\s*$",
        # More flexible patterns
        r"Mutual\s+Fund.*Folios?",
        r"MF.*Folios?",
        # Pattern that might appear in headers
        r"^\s*Mutual\s+Fund\s+Folios?\s+\d+\s+folios?\s+",
        # Generic folio patterns
        r"^.*Mutual.*Fund.*$",
    ]

    for i, line in enumerate(lines[start_idx:], start_idx):
        line_clean = line.strip()
        if not line_clean:
            continue

        for pattern in mf_section_patterns:
            if re.search(pattern, line_clean, flags=re.I):
                print(f"DEBUG: Found MF section at line {i}: '{line_clean}' with pattern: '{pattern}'")
                return True, i

    return False, -1


def extract_mf_holdings_data(lines, start_idx):
    """
    Extract MF holdings data from lines starting at start_idx.
    Uses multiple regex patterns and fallback parsing.
    """
    holdings = []

    # Multiple regex patterns for MF holdings
    patterns = [
        # Original pattern
        NSDL_MF_HOLDINGS_RE,
        # Alternative patterns with different whitespace handling
        r"(INF[0-9A-Z]{8}[0-9])\s*\n?\s*(.+?)\s*\n?\s*(.+?)\s+(\w+?)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)(?:\s+([\d,.]+))?\s*$",
        # Simplified pattern
        r"(INF[0-9A-Z]{8}[0-9])\s+(.+?)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s*$",
        # Tab-separated pattern
        r"(INF[0-9A-Z]{8}[0-9])\t+(.+?)\t+([\d,.]+)\t+([\d,.]+)\t+([\d,.]+)",
    ]

    amt_re = r"([(-]*\d[\d,.]+)\)*"

    for i, line in enumerate(lines[start_idx:], start_idx):
        line_clean = line.strip()
        if not line_clean:
            continue

        # Skip non-data lines
        if any(skip_word in line_clean.upper() for skip_word in
               ['ACCOUNT', 'HOLDER', 'CLIENT', 'TOTAL', 'SUBTOTAL', 'GRAND']):
            continue

        # Try each pattern
        matched = False
        for pattern_idx, pattern in enumerate(patterns):
            try:
                match = re.search(pattern, line, re.DOTALL | re.MULTILINE | re.I)
                if match:
                    groups = match.groups()
                    print(f"DEBUG: Pattern {pattern_idx} matched line {i}: {len(groups)} groups")

                    if len(groups) >= 5:  # Minimum required fields
                        isin = groups[0]
                        name = re.sub(r"\s+", " ", groups[1]).strip()
                        name = re.sub(r"[^a-zA-Z0-9_)]+$", "", name).strip()

                        # Handle different group arrangements based on pattern
                        if len(groups) >= 11:  # Full pattern
                            ucc, folio, units, avg_cost, total_cost, nav, value, pnl = groups[2:10]
                            returns = groups[10] if len(groups) > 10 else ""
                        elif len(groups) >= 8:  # Medium pattern
                            ucc, folio, units, avg_cost, nav, value, pnl = groups[2:9]
                            total_cost = ""
                            returns = groups[8] if len(groups) > 8 else ""
                        elif len(groups) >= 5:  # Simplified pattern
                            units, nav, value = groups[2:5]
                            ucc = folio = avg_cost = total_cost = pnl = returns = ""

                        record = {
                            "isin": isin,
                            "ucc": (ucc or "").strip(),
                            "name": name,
                            "folio": (folio or "").strip(),
                            "balance": units,
                            "avg_cost": avg_cost or "",
                            "total_cost": total_cost or "",
                            "nav": nav,
                            "value": value,
                            "pnl": pnl or "",
                            "return": returns or "",
                        }
                        holdings.append(record)
                        print(f"DEBUG: Added MF holding: {name[:50]}...")
                        matched = True
                        break

            except Exception as e:
                print(f"DEBUG: Pattern {pattern_idx} failed on line {i}: {e}")
                continue

        if not matched:
            # Try manual parsing for lines with ISIN
            if re.search(r"INF[0-9A-Z]{8}[0-9]", line_clean):
                print(f"DEBUG: Manual parsing attempt for line {i}: '{line_clean[:100]}...'")
                try:
                    # Simple manual extraction
                    parts = re.split(r'\s+', line_clean)
                    isin_part = None
                    for part in parts:
                        if re.match(r"INF[0-9A-Z]{8}[0-9]", part):
                            isin_part = part
                            break

                    if isin_part:
                        # Find numeric parts (likely balance, nav, value)
                        numeric_parts = [p for p in parts if re.match(r"[\d,.]+", p)]
                        if len(numeric_parts) >= 3:
                            record = {
                                "isin": isin_part,
                                "ucc": "",
                                "name": f"MF Fund {isin_part}",  # Placeholder name
                                "folio": "",
                                "balance": numeric_parts[0],
                                "avg_cost": "",
                                "total_cost": "",
                                "nav": numeric_parts[-2] if len(numeric_parts) >= 2 else "",
                                "value": numeric_parts[-1],
                                "pnl": "",
                                "return": "",
                            }
                            holdings.append(record)
                            print(f"DEBUG: Manual extraction successful for {isin_part}")

                except Exception as e:
                    print(f"DEBUG: Manual parsing failed: {e}")

    return holdings


def process_nsdl_text(text):
    hdr_data = parse_header(text[:1000])
    statement_period = StatementPeriod(from_=hdr_data["from"], to=hdr_data["to"])

    accounts = re.findall(
        DEMAT_HEADER_RE,
        text,
        flags=re.I | re.MULTILINE,
    )
    mutual_funds = re.findall(
        DEMAT_MF_HEADER_RE,
        text,
        flags=re.I | re.MULTILINE,
    )

    demat = {}
    for account_type, account_name, dp_id, client_id, folios, balance in accounts:
        demat[(dp_id, client_id)] = {
            "name": account_name,
            "folios": folios,
            "balance": balance,
            "type": account_type,
            "dp_id": dp_id,
            "client_id": client_id,
            "owners": [],
            "equities": [],
            "mutual_funds": [],
            "mf_folio_f": [],
            "corporate_bonds": [],
        }
    for num_folios, _, balance in mutual_funds:
        demat[(None, None)] = {
            "name": "Mutual Fund Folios",
            "folios": num_folios,
            "balance": balance,
            "type": "MF",
            "dp_id": "",
            "client_id": "",
            "owners": [],
            "equities": [],
            "mutual_funds": [],
            "mf_folio_f": [],
            "corporate_bonds": [],
        }

    lines = text.split("\u2029")
    start_processing_holdings = False
    current_demat = None
    demat_holders = []

    print(f"DEBUG: Processing {len(lines)} lines")

    # First pass: look for MF folio sections anywhere in the document
    mf_found, mf_start_line = detect_mf_folio_section(lines)

    if mf_found:
        print(f"DEBUG: MF section detected at line {mf_start_line}")

        # Ensure MF account exists
        if (None, None) not in demat:
            demat[(None, None)] = {
                "name": "Mutual Fund Folios",
                "folios": "0",
                "balance": "0.00",
                "type": "MF",
                "dp_id": "",
                "client_id": "",
                "owners": [],
                "equities": [],
                "mutual_funds": [],
                "mf_folio_f": [],
                "corporate_bonds": [],
            }

        # Extract MF holdings data
        mf_holdings = extract_mf_holdings_data(lines, mf_start_line + 1)

        if mf_holdings:
            demat[(None, None)]["mf_folio_f"] = mf_holdings
            # Also populate mutual_funds array
            for record in mf_holdings:
                demat[(None, None)]["mutual_funds"].append({
                    "isin": record["isin"],
                    "name": record["name"],
                    "balance": record["balance"],
                    "nav": record["nav"],
                    "value": record["value"],
                })
            print(f"DEBUG: Added {len(mf_holdings)} MF holdings to account")
        else:
            print("DEBUG: No MF holdings data extracted despite finding section")
    else:
        print("DEBUG: No MF section detected in document")

    # Continue with regular processing for other accounts
    for line in lines:
        if m := re.search(DEMAT_AC_TYPE_RE, line, flags=re.I):
            start_processing_holdings = True
            current_demat = None

        if not start_processing_holdings:
            continue

        if current_demat is None:
            # Check for account holders
            if "ACCOUNT HOLDER" in line.upper():
                for owner, pan in re.findall(DEMAT_AC_HOLDER_RE, line, re.I):
                    demat_holders.append({"name": owner, "PAN": pan})

            # Check for DP ID/Client ID
            if m := re.search(
                    DEMAT_DP_ID_RE,
                    line,
                    flags=re.I | re.MULTILINE | re.DOTALL,
            ):
                dp_id, client_id = m.groups()
                if (dp_id, client_id) in demat:
                    current_demat = demat[(dp_id, client_id)]
                    current_demat["owners"] = demat_holders.copy()
                demat_holders = []
            continue

        # Process holdings for NSDL/CDSL accounts
        if current_demat["type"] in ["NSDL", "NSDL Demat Account"]:
            # Try equity-like line
            if m := re.search(NSDL_EQ_RE, line, re.DOTALL | re.MULTILINE | re.I):
                isin, name, face_value, num_shares, market_value, current_value = m.groups()
                name_clean = re.sub(r"\s+", " ", name).strip()
                if looks_like_corporate_bond(name_clean):
                    current_demat["corporate_bonds"].append({
                        "isin": isin,
                        "name": name.strip(),
                        "quantity": num_shares,
                        "price": market_value,
                        "value": current_value,
                    })
                else:
                    current_demat["equities"].append({
                        "isin": isin,
                        "name": name.strip(),
                        "num_shares": num_shares,
                        "price": market_value,
                        "value": current_value,
                    })
                continue

            # MF inside NSDL account
            if m := re.search(NSDL_MF_RE, line, re.DOTALL | re.MULTILINE | re.I):
                isin, name, balance, nav, value = m.groups()
                current_demat["mutual_funds"].append({
                    "isin": isin,
                    "name": re.sub(r"\s+", " ", name).strip(),
                    "balance": balance,
                    "nav": nav,
                    "value": value,
                })
                continue

        elif current_demat["type"] in ["CDSL", "CDSL Demat Account"]:
            if m := re.search(NSDL_CDSL_HOLDINGS_RE, line, re.DOTALL | re.MULTILINE | re.I):
                isin, name, balance, *_, nav, value = m.groups()
                name_clean = re.sub(r"\s+", " ", name).strip()

                if isin.startswith("INF"):
                    current_demat["mutual_funds"].append({
                        "isin": isin,
                        "name": name_clean,
                        "balance": balance,
                        "nav": nav,
                        "value": value,
                    })
                elif isin.startswith("INE"):
                    if looks_like_corporate_bond(name_clean):
                        current_demat["corporate_bonds"].append({
                            "isin": isin,
                            "name": name_clean,
                            "quantity": balance,
                            "price": nav,
                            "value": value,
                        })
                    else:
                        current_demat["equities"].append({
                            "isin": isin,
                            "name": name_clean,
                            "num_shares": balance,
                            "price": nav,
                            "value": value,
                        })
                continue

    cas_data = NSDLCASData(
        statement_period=statement_period,
        accounts=list(demat.values()),
    )

    # ISIN lookup for missing names
    with ISINDb() as isin_db:
        for account in cas_data.accounts:
            # equities
            for equity in getattr(account, "equities", []):
                name = equity.get("name") if isinstance(equity, dict) else getattr(equity, "name", None)
                if not name:
                    isin_data = isin_db.isin_lookup(equity["isin"] if isinstance(equity, dict) else equity.isin)
                    if isin_data:
                        if isinstance(equity, dict):
                            equity["name"] = isin_data.name
                        else:
                            equity.name = isin_data.name
            # corporate bonds
            for bond in getattr(account, "corporate_bonds", []):
                name = bond.get("name") if isinstance(bond, dict) else getattr(bond, "name", None)
                if not name:
                    isin_data = isin_db.isin_lookup(bond["isin"] if isinstance(bond, dict) else bond.isin)
                    if isin_data:
                        if isinstance(bond, dict):
                            bond["name"] = isin_data.name
                        else:
                            bond.name = isin_data.name
            # MF holdings
            for mf in getattr(account, "mf_folio_f", []):
                if isinstance(mf, dict) and not mf.get("name"):
                    isin_data = isin_db.isin_lookup(mf["isin"])
                    if isin_data:
                        mf["name"] = isin_data.name

    # Final debug summary
    print(f"DEBUG: Final summary:")
    for account in cas_data.accounts:
        acc_dict = account if isinstance(account, dict) else account.__dict__
        mf_count = len(acc_dict.get("mf_folio_f", []))
        eq_count = len(acc_dict.get("equities", []))
        bond_count = len(acc_dict.get("corporate_bonds", []))
        print(
            f"  Account '{acc_dict.get('name', 'Unknown')}': {mf_count} MF folios, {eq_count} equities, {bond_count} bonds")

    return cas_data