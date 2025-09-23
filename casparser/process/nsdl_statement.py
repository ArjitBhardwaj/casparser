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
    NSDL_ISIN_RE,
    NSDL_AMT_RE,
    CDSL_ACCOUNT_RE,
    NSDL_ACCOUNT_RE,
    MF_SECTION_PATTERNS,
    get_detailed_mf_pattern,
    get_simple_mf_pattern,
)


def looks_like_corporate_bond(name: str) -> bool:
    """Heuristic: classify bond/NCD/NCB/debenture by name tokens."""
    if not name:
        return False
    norm = re.sub(r"[^A-Z0-9]+", " ", name.upper()).strip()
    return re.search(BOND_NAME_RE, norm, flags=re.I) is not None


def parse_header(text):
    """Parse CAS header data."""
    if m := re.search(
            DEMAT_STATEMENT_PERIOD_RE,
            text,
            re.DOTALL | re.MULTILINE | re.I,
    ):
        return m.groupdict()
    raise HeaderParseError("Error parsing CAS header")


def clean_fund_name(name):
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


def extract_mf_holdings_data(lines, start_idx, target_account=None):
    """Extract MF holdings data with improved parsing."""
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

        # For 2025 format, the data is spread across multiple lines in a specific pattern:
        # Line 1: ISIN + UCC + Fund Name + Folio
        # Line 2: Balance + AvgCost + TotalCost + NAV + Value + PnL + Return

        # Try to extract the complete record
        full_text = line
        lines_consumed = 1

        # Look ahead to gather all related lines
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

        # Try the detailed pattern for mf_folio_f sections
        # Pattern matches: ISIN UCC Name Folio Balance [SKIP_FIELD] AvgCost TotalCost NAV Value PnL Return
        detailed_pattern = (
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
            rf'\s+([\d,]+(?:\.\d+)?)'  # P&L
            rf'(?:\s+([\d,]+(?:\.\d+)?))?'  # Returns (optional)
        )

        detailed_match = re.search(detailed_pattern, full_text, re.DOTALL | re.I)

        if detailed_match:
            groups = detailed_match.groups()
            if len(groups) >= 9:  # Need at least 9 fields for detailed record (skipping one field)
                isin, raw_ucc, raw_name, folio, balance, avg_cost, total_cost, nav, value = groups[:9]
                pnl = groups[9] if len(groups) > 9 else ""
                returns = groups[10] if len(groups) > 10 else ""

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

                # Validate that we have reasonable data
                try:
                    balance_val = float(balance.replace(",", ""))
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

    # Only create standalone MF account if there are MF headers but no regular accounts
    for num_folios, _, balance in mutual_funds:
        if not demat:  # Only if no other accounts exist
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

    # Look for MF folio sections and associate them with the correct account
    for i, line in enumerate(lines):
        line_clean = line.strip()
        if not line_clean:
            continue

        # Check if this line indicates an MF section
        is_mf_section = False
        for pattern in MF_SECTION_PATTERNS:
            if re.search(pattern, line_clean, flags=re.I):
                is_mf_section = True
                break

        if is_mf_section:
            # Find which account this MF section belongs to
            account_context = find_account_context(lines, i)

            if account_context:
                account_type, account_name, dp_id, client_id = account_context
                target_key = (dp_id, client_id)

                # Extract MF holdings for this specific account
                mf_holdings = extract_mf_holdings_data(lines, i + 1, target_key)

                if mf_holdings and target_key in demat:
                    # Separate detailed and simple records
                    detailed_records = []
                    simple_records = []

                    for record in mf_holdings:
                        # If has detailed folio info, it's a detailed record
                        if record.get("folio") or record.get("ucc") or record.get("avg_cost"):
                            detailed_records.append(record)
                        else:
                            # Create simple mutual fund record
                            simple_records.append({
                                "isin": record["isin"],
                                "name": record["name"],
                                "balance": record["balance"],
                                "nav": record["nav"],
                                "value": record["value"],
                            })

                    # Store detailed records in mf_folio_f
                    demat[target_key]["mf_folio_f"].extend(detailed_records)

                    # Store simple records in mutual_funds (avoiding duplicates)
                    existing_isins = {mf.get("isin") for mf in demat[target_key]["mutual_funds"]}
                    for simple_record in simple_records:
                        if simple_record["isin"] not in existing_isins:
                            demat[target_key]["mutual_funds"].append(simple_record)

    # Continue with regular processing for other holdings
    start_processing_holdings = False
    current_demat = None
    demat_holders = []

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
        if current_demat and current_demat["type"] in ["NSDL", "NSDL Demat Account"]:
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

        elif current_demat and current_demat["type"] in ["CDSL", "CDSL Demat Account"]:
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
            # Fill missing names in mf_folio_f
            for mf in getattr(account, "mf_folio_f", []):
                if isinstance(mf, dict) and (
                        not mf.get("name") or mf.get("name") in ["NOT", "M", "MFBRLA0028", "MFPRUI0072", "MFPRUI0058",
                                                                 "MFPRUI0041", "MFKOTAK1233", "MFSBIM0043", "149091",
                                                                 "MFRILC0011"]):
                    isin_data = isin_db.isin_lookup(mf["isin"])
                    if isin_data:
                        mf["name"] = isin_data.name

            # Fill missing names in mutual_funds
            for mf in getattr(account, "mutual_funds", []):
                if isinstance(mf, dict):
                    # Clean corrupted names
                    if mf.get("name") and re.search(r'[\d,.]+ [\d,.]+ [\d,.]+ [\d,.]+', mf["name"]):
                        mf["name"] = clean_fund_name(mf["name"])

                    # Fill missing names
                    if not mf.get("name"):
                        isin_data = isin_db.isin_lookup(mf["isin"])
                        if isin_data:
                            mf["name"] = isin_data.name

            # Fill missing names in equities and bonds
            for equity in getattr(account, "equities", []):
                name = equity.get("name") if isinstance(equity, dict) else getattr(equity, "name", None)
                if not name:
                    isin_data = isin_db.isin_lookup(equity["isin"] if isinstance(equity, dict) else equity.isin)
                    if isin_data:
                        if isinstance(equity, dict):
                            equity["name"] = isin_data.name
                        else:
                            equity.name = isin_data.name

            for bond in getattr(account, "corporate_bonds", []):
                name = bond.get("name") if isinstance(bond, dict) else getattr(bond, "name", None)
                if not name:
                    isin_data = isin_db.isin_lookup(bond["isin"] if isinstance(bond, dict) else bond.isin)
                    if isin_data:
                        if isinstance(bond, dict):
                            bond["name"] = isin_data.name
                        else:
                            bond.name = isin_data.name

    return cas_data