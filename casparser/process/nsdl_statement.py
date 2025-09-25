import re

from casparser_isin import ISINDb

from casparser.exceptions import HeaderParseError
from casparser.types import NSDLCASData, StatementPeriod
from .data_extraction_utils import (
    find_account_context,
    extract_mf_holdings_data,
)
from .name_cleaning_utils import (
    clean_equity_name,
    clean_corporate_bond_name,
    clean_fund_name,
)
from .regex import (
    DEMAT_AC_HOLDER_RE,
    DEMAT_AC_TYPE_RE,
    DEMAT_DP_ID_RE,
    DEMAT_HEADER_RE,
    DEMAT_MF_HEADER_RE,
    DEMAT_STATEMENT_PERIOD_RE,
    NSDL_CDSL_HOLDINGS_RE,
    NSDL_EQ_RE,
    NSDL_MF_RE,
    MF_SECTION_PATTERNS,
)
from .validation_utils import (
    is_valid_fund_name,
    enhanced_looks_like_corporate_bond,
)


def parse_header(text):
    """Parse CAS header data."""
    if m := re.search(
            DEMAT_STATEMENT_PERIOD_RE,
            text,
            re.DOTALL | re.MULTILINE | re.I,
    ):
        return m.groupdict()
    raise HeaderParseError("Error parsing CAS header")

def process_nsdl_text(text):
    hdr_data = parse_header(text[:1000])
    statement_period = StatementPeriod(from_=hdr_data["from"], to=hdr_data["to"])

    # Extract year from statement period to determine parsing logic
    statement_year = None
    try:
        statement_year = int(hdr_data["to"].split("-")[-1])
    except (KeyError, ValueError, IndexError):
        # If we can't parse the year, default to newer format (2025+) to be safe
        # This ensures we use the more robust parsing logic by default
        statement_year = 2025

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

                # Extract MF holdings for this specific account - pass statement year
                mf_holdings = extract_mf_holdings_data(lines, i + 1, target_key, statement_year)

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

                # First determine if this is a corporate bond
                is_bond = enhanced_looks_like_corporate_bond(name)

                # Use appropriate cleaning function based on type
                if is_bond:
                    name_clean = clean_corporate_bond_name(name)
                else:
                    name_clean = clean_equity_name(name)

                name_clean = re.sub(r"\s+", " ", name_clean).strip()

                if is_bond:
                    current_demat["corporate_bonds"].append({
                        "isin": isin,
                        "name": name_clean,
                        "quantity": num_shares,
                        "price": market_value,
                        "value": current_value,
                    })
                else:
                    current_demat["equities"].append({
                        "isin": isin,
                        "name": name_clean,
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

                if isin.startswith("INF"):
                    # It's a mutual fund
                    name_clean = re.sub(r"\s+", " ", name).strip()
                    current_demat["mutual_funds"].append({
                        "isin": isin,
                        "name": name_clean,
                        "balance": balance,
                        "nav": nav,
                        "value": value,
                    })
                elif isin.startswith("INE"):
                    # Could be equity or corporate bond
                    is_bond = enhanced_looks_like_corporate_bond(name)

                    # Use appropriate cleaning function
                    if is_bond:
                        name_clean = clean_corporate_bond_name(name)
                    else:
                        name_clean = clean_equity_name(name)

                    name_clean = re.sub(r"\s+", " ", name_clean).strip()

                    if is_bond:
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
                if isinstance(mf, dict) and not is_valid_fund_name(mf.get("name")):
                    isin_data = isin_db.isin_lookup(mf["isin"])
                    if isin_data:
                        mf["name"] = isin_data.name

            # Fill missing names in mutual_funds
            for mf in getattr(account, "mutual_funds", []):
                if isinstance(mf, dict):
                    # Clean corrupted names first
                    if mf.get("name"):
                        cleaned_name = clean_fund_name(mf["name"])
                        if cleaned_name != mf["name"]:
                            mf["name"] = cleaned_name

                    # Fill missing or invalid names
                    if not is_valid_fund_name(mf.get("name")):
                        isin_data = isin_db.isin_lookup(mf["isin"])
                        if isin_data:
                            mf["name"] = isin_data.name

            # Fill missing names in equities (use equity cleaning)
            for equity in getattr(account, "equities", []):
                name = equity.get("name") if isinstance(equity, dict) else getattr(equity, "name", None)
                if not is_valid_fund_name(name):
                    isin_data = isin_db.isin_lookup(equity["isin"] if isinstance(equity, dict) else equity.isin)
                    if isin_data:
                        clean_name = clean_equity_name(isin_data.name)
                        if isinstance(equity, dict):
                            equity["name"] = clean_name
                        else:
                            equity.name = clean_name

            # Fill missing names in corporate bonds (use corporate bond cleaning)
            for bond in getattr(account, "corporate_bonds", []):
                name = bond.get("name") if isinstance(bond, dict) else getattr(bond, "name", None)
                if not is_valid_fund_name(name):
                    isin_data = isin_db.isin_lookup(bond["isin"] if isinstance(bond, dict) else bond.isin)
                    if isin_data:
                        clean_name = clean_corporate_bond_name(isin_data.name)
                        if isinstance(bond, dict):
                            bond["name"] = clean_name
                        else:
                            bond.name = clean_name

    return cas_data