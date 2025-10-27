"""Regular expressions for parsing various sections in CAS."""

date_re = r"(\d{2}-[A-Za-z]{3}-\d{4})"
amt_re = r"([(-]*\d[\d,.]+)\)*"

isin_re = r"[A-Z]{2}[0-9A-Z]{9}[0-9]{1}"

CAS_TYPE_RE = r"consolidated\s+account\s+(statement|summary)"
DETAILED_DATE_RE = r"(?P<from>\d{2}-[a-zA-Z]{3}-\d{4})\s+to\s+(?P<to>\d{2}-[a-zA-Z]{3}-\d{4})"
SUMMARY_DATE_RE = r"as\s+on\s+(?P<date>\d{2}-[a-zA-Z]{3}-\d{4})"
SUMMARY_ROW_RE = (
    r"(?P<folio>[\d/\s]+?)(?P<isin>[A-Z]{2}[0-9A-Z]{9}[0-9]{1})?\s+(?P<code>[ \w]+)-"
    r"(?P<name>.+?)\s+(?P<cost>[\d,.]+)?\s+(?P<balance>[\d,.]+)\t\t"
    r"(?P<date>\d{2}-[A-Za-z]{3}-\d{4})\t\t(?P<nav>[\d,.]+)\t\t(?P<value>[\d,.]+)"
    r"\t\t(?P<rta>\w+)\s*$"
)
SCHEME_TAIL_RE = r"(\n.+?)\t\t"

AMC_RE = r"^(.+?\s+(MF|Mutual\s*Fund)|franklin\s+templeton\s+investments)$"
FOLIO_RE = r"^Folio\s+No\s*:\s+([\d/\s]+\d)\s"
FOLIO_KV_RE = r"(PAN|KYC)\s*:\s*([A-Z]{5}\d{4}[A-Z]|OK|NOT OK)"

NOMINEE_RE = r"\s*Nominee\s+[1-3]\s*:\s*(.*?)" * 3 + r"$"

SCHEME_RE = (
    r"(?P<code>[\s\w]+-*[gdp]?)-\s*\d*\s*(?P<name>.+?)(?:\t\t|\(\s*Advis|ISIN).*?"
    r"Registrar\s*:\s*(?P<rta>[^\s]*).*$"
)
SCHEME_KV_RE = r"""(\w+)\s*:\s*([-\w]+)"""

REGISTRAR_RE = r"^\s*Registrar\s*:\s*(.*)\s*$"
OPEN_UNITS_RE = r"Opening\s+Unit\s+Balance.+?([\d,.]+)"
CLOSE_UNITS_RE = r"Closing\s+Unit\s+Balance.+?([\d,.]+)"
COST_RE = r"Total\s+Cost\s+Value\s*:.+?[INR\s]*([\d,.]+)"
VALUATION_RE = (
    r"(?:Valuation|Market\s+Value)\s+on\s+(\d{2}-[A-Za-z]{3}-\d{4})\s*:\s*INR\s*([\d,.]+)"
)
NAV_RE = r"NAV\s+on\s+(\d{2}-[A-Za-z]{3}-\d{4})\s*:\s*INR\s*([\d,.]+)"

# Normal Transaction entries
TRANSACTION_RE1 = rf"{date_re}\t\t([^0-9].*)\t\t{amt_re}\t\t{amt_re}\t\t{amt_re}\t\t{amt_re}"
# Zero unit transactions (ref: #88)
TRANSACTION_RE2 = rf"{date_re}\t\t([^0-9].*)\t\t{amt_re}\t\t(?:{amt_re})*\t\t{amt_re}\t\t{amt_re}"
# Segregated portfolio entries
TRANSACTION_RE3 = rf"{date_re}\t\t([^0-9].*)\t\t{amt_re}\t\t{amt_re}(?:\t\t{amt_re}\t\t{amt_re})*"
# Tax transactions
TRANSACTION_RE4 = rf"{date_re}\t\t([^0-9].*)\t\t{amt_re}(?:\t\t{amt_re}\t\t{amt_re}\t\t{amt_re})*"
DESCRIPTION_TAIL_RE = r"(\n.+?)(\t\t|$)"
DIVIDEND_RE = r"(?:div\.|dividend|idcw).+?(reinvest)*.*?@\s*Rs\.\s*([\d\.]+)(?:\s+per\s+unit)?"
SCHEME_TAIL_RE = r"(\n.+?)(?:\t\t|$)"


DEMAT_STATEMENT_PERIOD_RE = (
    r"for\s+the\s+period\s+from\s+(?P<from>\d{2}-[a-zA-Z0-9]{2,3}-\d{4})"
    r"\s+to\s+(?P<to>\d{2}-[a-zA-Z0-9]{2,3}-\d{4})"
)
DEMAT_HEADER_RE = (
    r"((?:CDSL|NSDL)\s+demat\s+account)\s+(.+?)\s*DP\s*Id\s*:\s*(.+?)"
    r"\s*Client\s*Id\s*:\s*(\d+)\s+(\d+)\s+([\d,.]+)"
)
DEMAT_MF_HEADER_RE = r"Mutual Fund Folios\s+(\d+)\s+folios?\s+(\d+)\s+([\d,.]+)"

# Enhanced patterns for detecting account types and MF sections
DEMAT_AC_TYPE_RE = r"^(NSDL|CDSL)\s+demat\s+account|Mutual\s+Fund\s+Folios?\s*(?:\(F\))?"

# More flexible MF type detection - handles variations in spacing and optional (F)
DEMAT_MF_TYPE_RE = r"^Mutual\s+Fund\s+Folios?\s*(?:\(F\))?\s*$"

DEMAT_AC_HOLDER_RE = r"([^\t\n]+?)\s*\(PAN\s*:\s*(.+?)\)"
DEMAT_DP_ID_RE = r"DP\s*Id\s*:\s*(.+?)\s*Client\s*Id\s*:\s*(\d+).+PAN"

# Fixed NSDL equity regex - simplified character class
NSDL_EQ_RE = (
    rf"^([A-Z]{{2}}[E9][0-9A-Z]{{8}}[0-9])"
    rf"[\s\u2029]*(.+?)[\s\u2029]*"
    rf"(?:[\d,.]+[\s\u2029]+)?"
    rf"([\d,.]+)[\s\u2029]+"
    rf"([\d,.]+|See\s+Note)[\s\u2029]+"
    rf"{amt_re}$"
)

NSDL_MF_RE = rf"^(INF[0-9A-Z]{{8}}[0-9]{{1}})\s*(.*?)\s*{amt_re}\s+{amt_re}\s+{amt_re}$"
NSDL_CDSL_HOLDINGS_RE = (
    r"^([A-Z]{2}[0-9A-Z]{9}[0-9]{1})\s*(.+?)\s+" + rf"{amt_re}\s+" * 10 + rf"{amt_re}$"
)

# Enhanced MF holdings regex with more flexible whitespace and optional fields
NSDL_MF_HOLDINGS_RE = (
    rf"({isin_re})\s*"                        # ISIN
    rf"(.+?)\s+"                              # Name (can span multiple lines)
    rf"(.+?)\s+"                              # UCC/Folio info
    rf"(\w+?)\s+"                             # Folio number
    rf"{amt_re}\s+"                           # Units/balance
    rf"{amt_re}\s+"                           # Avg cost
    rf"{amt_re}\s+"                           # Total cost
    rf"{amt_re}\s+"                           # NAV
    rf"{amt_re}\s+"                           # Value
    rf"{amt_re}"                              # PnL
    rf"(?:\s+{amt_re})?\s*$"                  # Optional returns
)

# Alternative MF holdings patterns for when the main one doesn't work
NSDL_MF_HOLDINGS_ALT1 = (
    rf"^({isin_re})\n"                        # ISIN on its own line
    rf"(.+?)\n"                               # Name on next line
    rf"(.+?)\t\t"                             # UCC/other info
    rf"(\w+?)\t\t"                            # Folio
    rf"{amt_re}\t\t"                          # Units
    rf"{amt_re}\t\t"                          # Avg cost
    rf"{amt_re}\t\t"                          # Total cost
    rf"{amt_re}\t\t"                          # NAV
    rf"{amt_re}\t\t"                          # Value
    rf"{amt_re}"                              # PnL
    rf"(?:\t\t{amt_re})?\s*$"                 # Optional returns
)

NSDL_MF_HOLDINGS_ALT2 = (
    rf"({isin_re})\s+"                        # ISIN
    rf"([^\t\n]+)\s+"                         # Name (non-tab, non-newline)
    rf"([^\t\n]*)\s+"                         # UCC (optional)
    rf"(\w*)\s+"                              # Folio (optional)
    rf"{amt_re}\s+"                           # Units
    rf"{amt_re}\s+"                           # NAV
    rf"{amt_re}\s*$"                          # Value
)

# Bond name detection regex
BOND_NAME_RE = (
    r"(?:"
    r"NCDS?|NCB|BOND|BONDS|DEBENTURE|DEBENTURES|"
    r"REDEEM|REDEMPT|RED\s*DT|REDDT|MATUR|MDT|"
    r"NON\s*CUM|NONCUM|CUMULATIVE|COUPON|YTM|TAX\s*FREE|TAXFREE|TRANCHE|"
    r"SECURED|SECRED|UNSECURED|"
    r"SR[\s\-]*\d+[A-Z]?|"      # SR-1, SR 2A etc.
    r"FV\s*RS\.?1?000|FVRS?1?000|F\.?V\.?R?S?1?000|F\s*V\s*R?S?1?000|"
    r"\d{1,2}\.\d{2}\s*%|[\s\-]\d{1,2}%"
    r")"
)

# Additional ISIN and amount regex patterns used in NSDL parsing
NSDL_ISIN_RE = r"INF[0-9A-Z]{8}[0-9]"
NSDL_AMT_RE = r"([(-]*[\d,.]+)\)*"

# Account detection patterns
CDSL_ACCOUNT_RE = r'(CDSL)\s+demat\s+account\s+(.+?)\s+DP\s+Id\s*:\s*(\d+)\s+Client\s+Id\s*:\s*(\d+)'
NSDL_ACCOUNT_RE = r'(NSDL)\s+demat\s+account\s+(.+?)\s+DP\s+Id\s*:\s*(.+?)\s+Client\s+Id\s*:\s*(\d+)'

# MF section patterns
MF_SECTION_PATTERNS = [
    r"^Mutual\s+Fund\s+Folios?\s*\(F\)\s*$",
    r"^Mutual\s+Fund\s+Folios?\s*$",
    r"^MF\s+Folios?\s*\(F\)\s*$",
    r"^MF\s+Folios?\s*$",
    r"Mutual\s+Fund.*Folios?",
]

# MF holdings detailed pattern (for mf_folio_f sections)
def get_detailed_mf_pattern():
    """Pattern for detailed MF records (mf_folio_f section)"""
    # This pattern matches the actual data structure from the 2025 format:
    # ISIN + UCC + Fund Name + Folio + Balance + AvgCost + TotalCost + NAV + Value + PnL + Returns
    return (
        r'([A-Z0-9]{12})'  # ISIN
        r'\s+'
        r'([A-Z0-9/\s]*?)'  # UCC (optional, can be "NOT AVAILABLE")
        r'\s+'
        r'(.+?)'  # Fund name
        r'\s+'
        r'(\d+(?:\.\d+)?)'  # Folio number
        r'\s+'
        r'([\d,]+\.?\d*)'  # Balance (units)
        r'\s+'
        r'([\d,]+\.?\d*)'  # Average cost per unit
        r'\s+'
        r'([\d,]+\.?\d*)'  # Total cost
        r'\s+'
        r'([\d,]+\.?\d*)'  # Current NAV
        r'\s+'
        r'([\d,]+\.?\d*)'  # Current value
        r'\s+'
        r'([(-]*[\d,]+\.?\d*)\)*'  # Profit/Loss (can be negative)
        r'(?:\s+([(-]*[\d,]+\.?\d*)?\)*)?'  # Returns percentage (optional, can be negative)
    )

# MF holdings simple pattern (for mutual_funds sections)
def get_simple_mf_pattern():
    return rf"({NSDL_ISIN_RE})\s+(.+?)\s+{NSDL_AMT_RE}\s+{NSDL_AMT_RE}\s+{NSDL_AMT_RE}\s*$"