"""Client API Evoliz : auth + buys + invoices.

Auth :
    POST https://www.evoliz.io/api/login
    body: {"public_key": ..., "secret_key": ...}
    réponse: {"access_token": "...", "expires_at": "...", "scopes": [...]}

Le token est implicitement scopé à une seule société côté Evoliz, donc on
appelle les endpoints "flat" sans /companies/{cid}/ :
    GET /api/v1/buys
    POST /api/v1/invoices
"""

from __future__ import annotations

import time
from typing import Any, Optional

import httpx

from . import db
from .config import settings
from .models import Buy


class EvolizClient:
    def __init__(self) -> None:
        self._token: Optional[str] = None
        self._token_exp: float = 0.0
        self._client = httpx.AsyncClient(timeout=30.0)
        self._paytypes: Optional[list[dict]] = None
        self._payterms: Optional[list[dict]] = None
        self._sale_classifications: Optional[list[dict]] = None

    async def aclose(self) -> None:
        await self._client.aclose()

    # ----- auth -----

    def reset(self) -> None:
        """\u00c0 appeler quand les credentials changent (via /settings)."""
        self._token = None
        self._token_exp = 0.0

    async def _login(self) -> str:
        pk, sk = db.get_credentials()
        if not pk or not sk:
            raise RuntimeError(
                "Cl\u00e9s API Evoliz manquantes \u2014 configurez-les via /settings."
            )
        r = await self._client.post(
            settings.evoliz_login_url,
            json={"public_key": pk, "secret_key": sk},
        )
        r.raise_for_status()
        data = r.json()
        token = data.get("access_token") or data.get("token")
        if not token:
            raise RuntimeError(f"Réponse login inattendue : {data}")
        self._token = token
        # /api/login renvoie access_token + expires_at + scopes (pas de companyid).
        # On parse expires_at si pr\u00e9sent, sinon on suppose ~1h.
        exp_iso = data.get("expires_at")
        if exp_iso:
            try:
                from datetime import datetime
                # format observ\u00e9 : 2026-04-09T10:33:02.000000Z
                dt = datetime.fromisoformat(exp_iso.replace("Z", "+00:00"))
                self._token_exp = dt.timestamp() - 60
            except Exception:
                self._token_exp = time.time() + 3500
        else:
            self._token_exp = time.time() + 3500
        return token

    async def _ensure_token(self) -> str:
        if not self._token or time.time() >= self._token_exp:
            await self._login()
        assert self._token
        return self._token

    async def _request(
        self, method: str, path: str, *, params=None, json=None
    ) -> dict:
        token = await self._ensure_token()
        url = f"{settings.evoliz_base_url}{path}"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        r = await self._client.request(
            method, url, params=params, json=json, headers=headers
        )
        if r.status_code == 401:
            # Token expiré côté serveur → re-login + retry une fois
            self._token = None
            token = await self._ensure_token()
            headers["Authorization"] = f"Bearer {token}"
            r = await self._client.request(
                method, url, params=params, json=json, headers=headers
            )
        if r.status_code >= 400:
            # Inclut le body Evoliz dans l'erreur pour faciliter le debug
            body = r.text[:1000]
            raise RuntimeError(
                f"HTTP {r.status_code} sur {method} {path} \u2014 {body}"
            )
        return r.json()

    # ----- endpoints -----

    async def get_billable_buys(self) -> list[Buy]:
        """Récupère tous les buys, paginés, et filtre billable=true côté client."""
        page = 1
        out: list[Buy] = []
        while True:
            data = await self._request(
                "GET", "/buys", params={"page": page, "per_page": 100}
            )
            for raw in data.get("data", []):
                buy = Buy.from_api(raw)
                if buy.billable and buy.client is not None:
                    out.append(buy)
            meta = data.get("meta") or {}
            last = meta.get("last_page", page)
            if page >= last:
                break
            page += 1
        return out

    async def get_client(self, clientid: int) -> dict:
        """Fiche client compl\u00e8te (adresse, SIRET, contact...)."""
        return await self._request("GET", f"/clients/{clientid}")

    async def get_paytypes(self) -> list[dict]:
        """Liste des modes de paiement (cach\u00e9e en m\u00e9moire)."""
        if self._paytypes is None:
            data = await self._request("GET", "/paytypes")
            self._paytypes = data.get("data", [])
        return self._paytypes

    async def get_payterms(self) -> list[dict]:
        """Liste des d\u00e9lais de paiement (cach\u00e9e en m\u00e9moire)."""
        if self._payterms is None:
            data = await self._request("GET", "/payterms")
            self._payterms = data.get("data", [])
        return self._payterms

    async def get_recent_invoices(self, since_date: str) -> list[dict]:
        """Liste les factures de vente, filtr\u00e9es c\u00f4t\u00e9 client par `since_date`.

        Note : l'endpoint flat /invoices n'accepte pas de filtre `created_after`,
        donc on pagine puis on filtre. La liste \u00e9tant typiquement tri\u00e9e par date
        d\u00e9croissante, on s'arr\u00eate d\u00e8s qu'on tombe sur une page enti\u00e8rement
        ant\u00e9rieure \u00e0 la date pour limiter les appels.
        """
        out: list[dict] = []
        page = 1
        while True:
            data = await self._request(
                "GET", "/invoices",
                params={"page": page, "per_page": 100},
            )
            page_data = data.get("data", [])
            kept = [
                inv for inv in page_data
                if (inv.get("documentdate") or "") >= since_date
            ]
            out.extend(kept)
            # Si la page est non vide ET aucune invoice n'a pass\u00e9 le filtre, on
            # est all\u00e9 trop loin dans le pass\u00e9 \u2014 on s'arr\u00eate.
            if page_data and not kept:
                break
            meta = data.get("meta") or {}
            if page >= meta.get("last_page", 1):
                break
            page += 1
        return out

    async def get_sale_classifications(self) -> list[dict]:
        """Classifications de vente (cach\u00e9es). On filtre les enabled."""
        if self._sale_classifications is None:
            # Pagination compl\u00e8te (peut d\u00e9passer 100)
            out, page = [], 1
            while True:
                data = await self._request(
                    "GET", "/sale-classifications",
                    params={"page": page, "per_page": 100},
                )
                out.extend(data.get("data", []))
                meta = data.get("meta") or {}
                if page >= meta.get("last_page", 1):
                    break
                page += 1
            self._sale_classifications = [c for c in out if c.get("enabled", True)]
        return self._sale_classifications

    async def create_invoice(self, payload: dict[str, Any]) -> dict:
        return await self._request("POST", "/invoices", json=payload)


# Singleton accessible depuis FastAPI
client = EvolizClient()
