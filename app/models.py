from dataclasses import dataclass
from typing import Optional


@dataclass
class Supplier:
    supplierid: int
    code: str
    name: str


@dataclass
class Client:
    clientid: int
    code: str
    name: str


@dataclass
class BuyTotal:
    vat_exclude: float
    vat: Optional[float]
    vat_include: float


@dataclass
class Buy:
    buyid: int
    document_number: str
    external_document_number: Optional[str]
    documentdate: str  # ISO YYYY-MM-DD
    label: str
    supplier: Supplier
    client: Optional[Client]
    billable: bool
    total: BuyTotal
    currency_code: str

    @classmethod
    def from_api(cls, raw: dict) -> "Buy":
        sup = raw.get("supplier") or {}
        cli = raw.get("client")
        tot = raw.get("total") or {}
        cur = raw.get("default_currency") or {}
        return cls(
            buyid=raw["buyid"],
            document_number=raw.get("document_number", ""),
            external_document_number=raw.get("external_document_number"),
            documentdate=raw.get("documentdate", ""),
            label=(raw.get("label") or "").replace("\r\n", " — ").strip(),
            supplier=Supplier(
                supplierid=sup.get("supplierid", 0),
                code=sup.get("code", ""),
                name=sup.get("name", ""),
            ),
            client=(
                Client(
                    clientid=cli.get("clientid", 0),
                    code=cli.get("code", ""),
                    name=cli.get("name", ""),
                )
                if cli
                else None
            ),
            billable=bool(raw.get("billable")),
            total=BuyTotal(
                vat_exclude=float(tot.get("vat_exclude") or 0),
                vat=(float(tot["vat"]) if tot.get("vat") is not None else None),
                vat_include=float(tot.get("vat_include") or 0),
            ),
            currency_code=cur.get("code", "EUR"),
        )

    def vat_rate(self) -> float:
        """Déduit un taux de TVA standard FR à partir des montants."""
        if not self.total.vat or self.total.vat_exclude == 0:
            return 0.0
        ratio = self.total.vat / self.total.vat_exclude * 100
        for std in (20.0, 10.0, 5.5, 2.1, 0.0):
            if abs(ratio - std) < 0.5:
                return std
        return round(ratio, 2)
