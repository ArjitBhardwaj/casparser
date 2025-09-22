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
            "corporate_bonds": [],  # <-- NEW
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
            "corporate_bonds": [],  # <-- NEW
        }

    lines = text.split("\u2029")
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
            if m := re.search(DEMAT_MF_TYPE_RE, line.strip(), flags=re.I):
                if (None, None) in demat:
                    current_demat = demat[(None, None)]
                else:
                    continue

            if "ACCOUNT HOLDER" in line.upper():
                for owner, pan in re.findall(DEMAT_AC_HOLDER_RE, line, re.I):
                    demat_holders.append({"name": owner, "PAN": pan})

            if m := re.search(
                DEMAT_DP_ID_RE,
                line,
                flags=re.I | re.MULTILINE | re.DOTALL,
            ):
                dp_id, client_id = m.groups()
                # guard: only proceed if we actually have this account header
                if (dp_id, client_id) in demat:
                    current_demat = demat[(dp_id, client_id)]
                    current_demat["owners"] = demat_holders.copy()
                demat_holders = []
            continue

        # --- Holdings classification by account type ---
        if "NSDL" in current_demat["type"]:
            # Try equity-like line (also used by bonds; classification by name)
            if m := re.search(NSDL_EQ_RE, line, re.DOTALL | re.MULTILINE | re.I):
                isin, name, face_value, num_shares, market_value, current_value = m.groups()
                name_clean = re.sub(r"\s+", " ", name).strip()
                if looks_like_corporate_bond(name_clean):
                    current_demat["corporate_bonds"].append(
                        {
                            "isin": isin,
                            "name": name.strip(),
                            "quantity": num_shares,  # bonds also show a 'qty' in CAS
                            "price": market_value,   # last price/clean price in table
                            "value": current_value,  # current market value
                        }
                    )
                else:
                    current_demat["equities"].append(
                        {
                            "isin": isin,
                            "name": name.strip(),
                            # "face_value": face_value,  # keep if you need
                            "num_shares": num_shares,
                            "price": market_value,
                            "value": current_value,
                        }
                    )
                continue

            # MF inside NSDL account
            if m := re.search(NSDL_MF_RE, line, re.DOTALL | re.MULTILINE | re.I):
                isin, name, balance, nav, value = m.groups()
                current_demat["mutual_funds"].append(
                    {
                        "isin": isin,
                        "name": re.sub(r"\s+", " ", name).strip(),
                        "balance": balance,
                        "nav": nav,
                        "value": value,
                    }
                )
                continue

        elif "CDSL" in current_demat["type"]:
            if m := re.search(NSDL_CDSL_HOLDINGS_RE, line, re.DOTALL | re.MULTILINE | re.I):
                isin, name, balance, *_, nav, value = m.groups()
                name_clean = re.sub(r"\s+", " ", name).strip()

                if isin.startswith("INF"):
                    # MF through CDSL
                    current_demat["mutual_funds"].append(
                        {
                            "isin": isin,
                            "name": name_clean,
                            "balance": balance,
                            "nav": nav,
                            "value": value,
                        }
                    )
                elif isin.startswith("INE"):
                    # Could be equity or corporate bond; decide by name
                    if looks_like_corporate_bond(name_clean):
                        current_demat["corporate_bonds"].append(
                            {
                                "isin": isin,
                                "name": name_clean,
                                "quantity": balance,
                                "price": nav,
                                "value": value,
                            }
                        )
                    else:
                        current_demat["equities"].append(
                            {
                                "isin": isin,
                                "name": name_clean,
                                "num_shares": balance,
                                "price": nav,
                                "value": value,
                            }
                        )
                continue

        elif current_demat["type"] == "MF":
            if m := re.search(NSDL_MF_HOLDINGS_RE, line, re.DOTALL | re.MULTILINE | re.I):
                (
                    isin, ucc, name, folio, units, avg_cost, total_cost,
                    nav, value, pnl, returns
                ) = m.groups()
                name = re.sub(r"\s+", " ", name).strip()
                name = re.sub(r"[^a-zA-Z0-9_)]+$", "", name).strip()
                current_demat["mutual_funds"].append(
                    {
                        "isin": isin,
                        "ucc": ucc,
                        "name": name,
                        "folio": folio,
                        "balance": units,
                        "avg_cost": avg_cost,
                        "total_cost": total_cost,
                        "nav": nav,
                        "value": value,
                        "pnl": pnl,
                        "return": returns,
                    }
                )

    cas_data = NSDLCASData(
        statement_period=statement_period,
        accounts=list(demat.values()),
    )

    # Optional: try to fill missing names for both equities and bonds via ISIN DB
    with ISINDb() as isin_db:
        for account in cas_data.accounts:
            # equities
            for equity in getattr(account, "equities", []):
                # If account.equities are dicts (not models), use .get; else attributes
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

    return cas_data
