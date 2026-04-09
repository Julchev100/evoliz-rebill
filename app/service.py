"""Logique métier : scan, regroupement, génération de factures de vente."""

from __future__ import annotations

import asyncio
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Optional

from . import db
from .evoliz import client
from .models import Buy, Client

# Marqueur ins\u00e9r\u00e9 dans le commentaire des factures g\u00e9n\u00e9r\u00e9es. Permet de
# d\u00e9tecter quelles factures d'achat ont d\u00e9j\u00e0 \u00e9t\u00e9 refactur\u00e9es \u2014 source de
# v\u00e9rit\u00e9 c\u00f4t\u00e9 Evoliz, donc immune \u00e0 un wipe du filesystem (HF Spaces).
REBILL_TAG_RE = re.compile(r"\[BUYS:([\d,\s]+)\]")
# Fen\u00eatre de scan des factures pour reconstruire l'historique
LOOKBACK_MONTHS = 12


@dataclass
class ClientGroup:
    client: Client
    buys: list[Buy]
    details: Optional[dict] = None  # fiche compl\u00e8te /clients/{id}
    enrich_error: Optional[str] = None

    @property
    def total_ht(self) -> float:
        return round(sum(b.total.vat_exclude for b in self.buys), 2)

    @property
    def address_lines(self) -> list[str]:
        if not self.details:
            return []
        addr = self.details.get("address") or {}
        lines = [
            addr.get("addr"),
            addr.get("addr2"),
            addr.get("addr3"),
        ]
        city = " ".join(filter(None, [addr.get("postcode"), addr.get("town")]))
        if city:
            lines.append(city)
        country = (addr.get("country") or {}).get("label")
        if country and country != "France":
            lines.append(country)
        return [l for l in lines if l]

    @property
    def siret(self) -> str:
        if not self.details:
            return ""
        v = self.details.get("business_number") or ""
        return "" if v in ("N/C", "") else v

    @property
    def vat_number(self) -> str:
        if not self.details:
            return ""
        v = self.details.get("vat_number") or ""
        return "" if v in ("N/C", "") else v

    @property
    def phone(self) -> str:
        if not self.details:
            return ""
        return self.details.get("phone") or self.details.get("mobile") or ""


@dataclass
class GenerationResult:
    client_name: str
    invoiceid: int | None
    invoice_number: str | None
    nb_buys: int
    error: str | None = None


async def _enrich(group: ClientGroup) -> None:
    try:
        group.details = await client.get_client(group.client.clientid)
    except Exception as e:  # noqa: BLE001
        group.enrich_error = str(e)


async def fetch_rebilled_buyids() -> set[int]:
    """R\u00e9cup\u00e8re l'ensemble des `buyid` d\u00e9j\u00e0 refactur\u00e9s en parsant les
    commentaires des factures de vente r\u00e9centes (LOOKBACK_MONTHS).

    Source de v\u00e9rit\u00e9 = Evoliz, pas SQLite \u2014 r\u00e9siste \u00e0 un reset du
    filesystem.
    """
    since = (date.today() - timedelta(days=LOOKBACK_MONTHS * 31)).isoformat()
    invoices = await client.get_recent_invoices(since)
    out: set[int] = set()
    for inv in invoices:
        comment = inv.get("comment_clean") or inv.get("comment") or ""
        for m in REBILL_TAG_RE.finditer(comment):
            for s in m.group(1).split(","):
                s = s.strip()
                if s.isdigit():
                    out.add(int(s))
    # Belt-and-suspenders : union avec SQLite local si dispo (utile en local
    # pour des achats marqu\u00e9s avant l'introduction des tags).
    out.update(db.rebilled_set())
    return out


async def scan_pending() -> list[ClientGroup]:
    """Liste les achats refacturables non encore traités, groupés par client.

    Chaque groupe est enrichi en parall\u00e8le avec la fiche compl\u00e8te
    `/clients/{clientid}` (adresse, SIRET, etc.).
    """
    buys, already = await asyncio.gather(
        client.get_billable_buys(),
        fetch_rebilled_buyids(),
    )
    groups: dict[int, ClientGroup] = {}
    for b in buys:
        if b.buyid in already or b.client is None:
            continue
        g = groups.get(b.client.clientid)
        if g is None:
            g = ClientGroup(client=b.client, buys=[])
            groups[b.client.clientid] = g
        g.buys.append(b)
    # Tri : client par nom, achats par date
    for g in groups.values():
        g.buys.sort(key=lambda x: x.documentdate)
    sorted_groups = sorted(groups.values(), key=lambda g: g.client.name.lower())
    # Enrichissement parall\u00e8le
    if sorted_groups:
        await asyncio.gather(*(_enrich(g) for g in sorted_groups))
    return sorted_groups


def build_invoice_payload(
    client_obj: Client,
    buys: list[Buy],
    paytypeid: int,
    paytermid: int,
    sale_classificationid: int,
) -> dict[str, Any]:
    """Construit le JSON pour POST /invoices en brouillon."""
    items = []
    for b in buys:
        ref = f" (réf {b.external_document_number})" if b.external_document_number else ""
        designation = f"{b.supplier.name} — {b.label}{ref}".strip(" —")
        items.append(
            {
                "designation": designation[:250],
                "quantity": 1,
                "unit": "U",
                "unit_price_vat_exclude": round(b.total.vat_exclude, 2),
                "vat": b.vat_rate(),
                "sale_classificationid": sale_classificationid,
            }
        )
    # Marqueur de tracabilit\u00e9 : permet de retrouver les buys d\u00e9j\u00e0 refactur\u00e9s
    # en lisant les commentaires des invoices Evoliz (cf. fetch_rebilled_buyids)
    buyids = ",".join(str(b.buyid) for b in buys)
    return {
        "clientid": client_obj.clientid,
        "documentdate": date.today().isoformat(),
        "object": "Refacturation de frais",
        "comment": (
            f"Facture g\u00e9n\u00e9r\u00e9e automatiquement par evoliz-rebill [BUYS:{buyids}]"
        ),
        "term": {
            "paytypeid": paytypeid,
            "paytermid": paytermid,
        },
        "items": items,
    }


async def generate_invoices(
    selection: dict[int, list[int]],
    paytypeid: int,
    paytermid: int,
    sale_classificationid: int,
) -> list[GenerationResult]:
    """Pour chaque client → liste de buyid sélectionnés, crée 1 facture brouillon."""
    # On rescanne pour avoir les objets Buy à jour, puis on filtre par sélection.
    groups = await scan_pending()
    by_client = {g.client.clientid: g for g in groups}
    results: list[GenerationResult] = []

    for clientid, buyids in selection.items():
        group = by_client.get(clientid)
        if not group:
            results.append(
                GenerationResult(
                    client_name=f"client {clientid}",
                    invoiceid=None,
                    invoice_number=None,
                    nb_buys=0,
                    error="Client introuvable dans le scan courant",
                )
            )
            continue

        wanted = set(buyids)
        selected = [b for b in group.buys if b.buyid in wanted]
        if not selected:
            continue

        payload = build_invoice_payload(
            group.client, selected, paytypeid, paytermid, sale_classificationid
        )
        try:
            resp = await client.create_invoice(payload)
        except Exception as e:  # noqa: BLE001
            results.append(
                GenerationResult(
                    client_name=group.client.name,
                    invoiceid=None,
                    invoice_number=None,
                    nb_buys=len(selected),
                    error=str(e),
                )
            )
            continue

        # La réponse contient typiquement l'invoice créée (data ou racine).
        inv = resp.get("data", resp) if isinstance(resp, dict) else {}
        invoiceid = inv.get("invoiceid") or inv.get("id") or 0
        invoice_number = inv.get("document_number") or inv.get("number")

        for b in selected:
            db.mark_rebilled(b.buyid, invoiceid, invoice_number)

        results.append(
            GenerationResult(
                client_name=group.client.name,
                invoiceid=invoiceid,
                invoice_number=invoice_number,
                nb_buys=len(selected),
            )
        )

    return results
