from collections import defaultdict
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import db, service
from .auth import require_auth
from .evoliz import client as evoliz_client

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Toutes les routes sont prot\u00e9g\u00e9es si APP_PASSWORD est d\u00e9fini
app = FastAPI(title="evoliz-rebill", dependencies=[Depends(require_auth)])


@app.on_event("startup")
async def _startup() -> None:
    db.init()


@app.on_event("shutdown")
async def _shutdown() -> None:
    await evoliz_client.aclose()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if not db.has_credentials():
        return RedirectResponse(url="/settings", status_code=303)
    try:
        groups = await service.scan_pending()
        paytypes = await evoliz_client.get_paytypes()
        payterms = await evoliz_client.get_payterms()
        classifications = await evoliz_client.get_sale_classifications()
        error = None
    except Exception as e:  # noqa: BLE001
        groups = []
        paytypes = []
        payterms = []
        classifications = []
        error = str(e)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "groups": groups,
            "paytypes": paytypes,
            "payterms": payterms,
            "classifications": classifications,
            "error": error,
        },
    )


@app.get("/settings", response_class=HTMLResponse)
async def settings_form(request: Request, saved: bool = False):
    pk = db.get_setting("evoliz_public_key") or ""
    sk = db.get_setting("evoliz_secret_key") or ""
    sk_masked = ("\u2022" * 8 + sk[-4:]) if sk else ""
    return templates.TemplateResponse(
        request,
        "settings.html",
        {"pk": pk, "sk_masked": sk_masked, "has_sk": bool(sk), "saved": saved},
    )


@app.post("/settings")
async def settings_save(
    public_key: str = Form(...),
    secret_key: str = Form(""),
):
    pk = public_key.strip()
    sk = secret_key.strip()
    if pk:
        db.set_setting("evoliz_public_key", pk)
    if sk:
        db.set_setting("evoliz_secret_key", sk)
    evoliz_client.reset()
    return RedirectResponse(url="/settings?saved=1", status_code=303)


@app.post("/generate", response_class=HTMLResponse)
async def generate(request: Request):
    form = await request.form()
    # Champs cochés : name="buy" value="{clientid}:{buyid}"
    selection: dict[int, list[int]] = defaultdict(list)
    for raw in form.getlist("buy"):
        try:
            cid_str, bid_str = raw.split(":", 1)
            selection[int(cid_str)].append(int(bid_str))
        except ValueError:
            continue
    try:
        paytypeid = int(form.get("paytypeid") or 0)
        paytermid = int(form.get("paytermid") or 0)
        classificationid = int(form.get("sale_classificationid") or 0)
    except ValueError:
        paytypeid = paytermid = classificationid = 0
    results = await service.generate_invoices(
        selection, paytypeid, paytermid, classificationid
    )
    return templates.TemplateResponse(
        request, "partials/result.html", {"results": results}
    )


@app.get("/history", response_class=HTMLResponse)
async def history(request: Request):
    rows = db.list_rebilled()
    return templates.TemplateResponse(
        request, "history.html", {"rows": rows}
    )
