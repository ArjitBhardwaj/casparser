from datetime import date
from decimal import Decimal
from typing import List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import CASFileType, FileType, TransactionType


class StatementPeriod(BaseModel):
    from_: str = Field(alias="from")
    to: str
    model_config = ConfigDict(populate_by_name=True)


class InvestorInfo(BaseModel):
    """Investor Info data structure."""

    name: str
    email: str
    address: str
    mobile: str


class TransactionData(BaseModel):
    """Mutual fund scheme transaction."""

    date: Union[date, str]
    description: str
    amount: Union[Decimal, float, None] = None
    units: Union[Decimal, float, None] = None
    nav: Union[Decimal, float, None] = None
    balance: Union[Decimal, float, None] = None
    type: TransactionType
    dividend_rate: Union[Decimal, float, None] = None


class SchemeValuation(BaseModel):
    """Scheme valuation as of a given date."""

    date: Union[date, str]
    nav: Union[Decimal, float]
    cost: Union[Decimal, float, None] = None
    value: Union[Decimal, float]


class Scheme(BaseModel):
    """Mutual Fund Scheme data structure."""

    scheme: str
    advisor: Optional[str] = None
    rta_code: str
    rta: str
    type: Optional[str] = None
    isin: Optional[str] = None
    amfi: Optional[str] = None
    nominees: List[str] = []
    open: Union[Decimal, float]
    close: Union[Decimal, float]
    close_calculated: Union[Decimal, float]
    valuation: SchemeValuation
    transactions: List[TransactionData]


class Folio(BaseModel):
    """Mutual Fund Folio data structure."""

    folio: str
    amc: str
    PAN: Optional[str] = None
    KYC: Optional[str] = None
    PANKYC: Optional[str] = None
    schemes: List[Scheme]


class CASData(BaseModel):
    """CAS Parser return data type."""

    statement_period: StatementPeriod
    folios: List[Folio]
    investor_info: InvestorInfo
    cas_type: CASFileType
    file_type: FileType
    model_config = ConfigDict(
        populate_by_name=True,
        use_enum_values=True,
    )


class PartialCASData(BaseModel):
    """CAS Parser return data type."""

    investor_info: InvestorInfo
    file_type: FileType
    lines: List[str]


class ProcessedCASData(BaseModel):
    cas_type: CASFileType
    folios: List[Folio]
    statement_period: StatementPeriod


class DematOwner(BaseModel):
    name: str
    PAN: str


class Equity(BaseModel):
    name: Optional[str] = None
    isin: str
    num_shares: Decimal
    price: Decimal
    value: Decimal

    @model_validator(mode="before")
    @classmethod
    def fix_float(cls, data: dict):
        for k, v in data.items():
            if (
                k in cls.__annotations__
                and issubclass(Decimal, cls.__annotations__[k])
                and isinstance(v, str)
            ):
                data[k] = v.replace(",", "_").replace("_", "")
        return data



class MutualFund(BaseModel):
    name: Optional[str] = None
    isin: str
    balance: Decimal
    nav: Decimal
    value: Decimal

    @model_validator(mode="before")
    @classmethod
    def fix_float(cls, data: dict):
        for k, v in data.items():
            if (
                k in cls.__annotations__
                and issubclass(Decimal, cls.__annotations__[k])
                and isinstance(v, str)
            ):
                data[k] = v.replace(",", "_").replace("_", "")
        return data


class MutualFundFolioF(BaseModel):
    name: Optional[str] = None
    isin: str
    ucc: Optional[str] = None
    folio: Optional[str] = None
    balance: Union[Decimal, float, None] = None
    avg_cost: Union[Decimal, float, None] = None
    total_cost: Union[Decimal, float, None] = None
    nav: Union[Decimal, float, None] = None
    value: Union[Decimal, float, None] = None
    pnl: Union[Decimal, float, None] = None
    return_rate: Union[Decimal, float, None] = Field(default=None, alias="return")

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="before")
    @classmethod
    def fix_float(cls, data: dict):
        if data is None:
            return data
        cleaned = dict(data)
        numeric_fields = {
            "balance",
            "avg_cost",
            "total_cost",
            "nav",
            "value",
            "pnl",
            "return",
            "return_rate",
        }
        for key, value in list(cleaned.items()):
            if isinstance(value, str):
                val = value.strip()
                if val in {"--", "-", ""}:
                    cleaned[key] = None
                    continue
                if key in numeric_fields:
                    if val.startswith("(") and val.endswith(")"):
                        val = f"-{val[1:-1]}"
                    cleaned[key] = val.replace(",", "")
        if "return" in cleaned and "return_rate" not in cleaned:
            cleaned["return_rate"] = cleaned.pop("return")
        return cleaned

class CorporateBond(BaseModel):
    name: Optional[str] = None
    isin: str
    # CAS usually shows quantity/face value/price/value. We keep these minimal.
    quantity: Decimal  # e.g., number of debentures/bonds
    price: Decimal     # per-unit price shown in CAS table
    value: Decimal     # total market value

    @model_validator(mode="before")
    @classmethod
    def fix_float(cls, data: dict):
        # Make Decimal fields robust to "1,234.56" strings
        for k, v in data.items():
            if (
                k in cls.__annotations__
                and issubclass(Decimal, cls.__annotations__[k])
                and isinstance(v, str)
            ):
                data[k] = v.replace(",", "_").replace("_", "")
        return data

class DematAccount(BaseModel):
    name: str
    type: str
    dp_id: Optional[str] = ""
    client_id: Optional[str] = ""
    folios: int
    balance: Decimal
    owners: List[DematOwner]
    equities: List[Equity]
    mutual_funds: List[MutualFund]
    mf_folio_f: List[MutualFundFolioF] = Field(default_factory=list)
    corporate_bonds: List[CorporateBond] = Field(default_factory=list)  # <-- NEW

    @model_validator(mode="before")
    @classmethod
    def fix_float(cls, data: dict):
        for k, v in data.items():
            try:
                if (
                    k in cls.__annotations__
                    and issubclass(Decimal, cls.__annotations__[k])
                    and isinstance(v, str)
                ):
                    data[k] = v.replace(",", "_").replace("_", "")
            except TypeError:
                # typing constructs like List[...] will land here; ignore
                pass
        return data



class NSDLCASData(BaseModel):
    accounts: List[DematAccount]
    statement_period: StatementPeriod
    investor_info: Optional[InvestorInfo] = None
    file_type: Optional[FileType] = None
    model_config = ConfigDict(
        populate_by_name=True,
        use_enum_values=True,
    )
