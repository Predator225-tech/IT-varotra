from datetime import datetime, timedelta, timezone
import asyncio
import json
from pathlib import Path
import os
import re
import secrets
import time
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import StreamingResponse
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field, EmailStr

from .services import invoice_message, sending_links
from .event_bus import EventBus, create_event_bus
from webauthn import (generate_authentication_options, generate_registration_options,
                      verify_authentication_response, verify_registration_response)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url, options_to_json_dict
from webauthn.helpers.structs import (AuthenticatorSelectionCriteria,
                                      PublicKeyCredentialDescriptor,
                                      UserVerificationRequirement)


SECRET = os.getenv("JWT_SECRET", "development-secret-change-me")
ALGORITHM = "HS256"
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
INVOICE_DIR = Path(os.getenv("INVOICE_DIR", "invoice"))
INVOICE_DIR.mkdir(parents=True, exist_ok=True)
SYNC_FILE = Path(os.getenv("SYNC_FILE", "data/campus-shop.json"))
SYNC_FILE.parent.mkdir(parents=True, exist_ok=True)
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

app = FastAPI(title="Campus Shop API", version="1.0.0")
event_bus: EventBus = create_event_bus()
event_tickets: dict[str, float] = {}
ticket_requests: dict[str, list[float]] = {}
WEBAUTHN_RP_ID = os.getenv("WEBAUTHN_RP_ID", "localhost")
WEBAUTHN_ORIGINS = [origin.strip() for origin in os.getenv(
    "WEBAUTHN_ORIGIN", "https://localhost:8443"
).split(",") if origin.strip()]
biometric_challenges: dict[str, bytes] = {}
biometric_credentials: dict[str, dict[str, dict[str, object]]] = {}
origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def prevent_stale_data(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class Product(BaseModel):
    id: int
    nom: str
    prix_achat: int = Field(ge=0)
    prix_vente: int = Field(ge=0)
    stock: int = Field(ge=0)
    facilite_paiement: bool = False
    nb_tranches: int | None = Field(default=None, ge=2, le=6)
    intervalle_jours: int | None = Field(default=None)


class ProductInput(BaseModel):
    nom: str = Field(min_length=1, max_length=150)
    prix_achat: int = Field(ge=0)
    prix_vente: int = Field(ge=0)
    stock: int = Field(ge=0)
    facilite_paiement: bool = False
    nb_tranches: int | None = Field(default=None, ge=2, le=6)
    intervalle_jours: int | None = None


class SendingLinkRequest(BaseModel):
    canal: str
    destinataire: str
    numero_facture: int
    date_vente: str
    client: str
    produit: str
    quantite: int
    total: int
    paye: int
    reste: int


class SyncPayload(BaseModel):
    P: list[dict]
    S: list[dict]
    n: int


PRODUCTS = [
    Product(id=1, nom="Clé USB 32 Go", prix_achat=18000, prix_vente=25000, stock=60,
            facilite_paiement=True, nb_tranches=2, intervalle_jours=14),
    Product(id=2, nom="Powerbank 10 000 mAh", prix_achat=45000, prix_vente=60000, stock=30,
            facilite_paiement=True, nb_tranches=3, intervalle_jours=14),
    Product(id=3, nom="Cahier 200 pages", prix_achat=2000, prix_vente=3000, stock=200),
    Product(id=4, nom="Écouteurs filaires", prix_achat=6000, prix_vente=10000, stock=40),
]


def current_user(token: Annotated[str, Depends(oauth2)]) -> str:
    try:
        data = jwt.decode(token, SECRET, algorithms=[ALGORITHM])
        username = data.get("sub")
        if not username:
            raise ValueError
        return str(username)
    except (JWTError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Jeton invalide ou expiré") from exc


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if digits.startswith("261"):
        return digits
    return "261" + digits.removeprefix("0")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def webauthn_context(request: Request) -> tuple[str, str]:
    origin = request.headers.get("origin")
    if not origin:
        forwarded_host = request.headers.get("x-forwarded-host", request.headers.get("host", "localhost"))
        forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        origin = f"{forwarded_proto}://{forwarded_host}"
    if origin not in WEBAUTHN_ORIGINS:
        raise HTTPException(status_code=400, detail="Origine WebAuthn non autorisée")
    hostname = urlsplit(origin).hostname
    if not hostname:
        raise HTTPException(status_code=400, detail="Origine WebAuthn invalide")
    return hostname, origin


def biometric_store(rp_id: str) -> dict[str, dict[str, object]]:
    return biometric_credentials.setdefault(rp_id, {})


@app.get("/api/biometrie/inscription/options")
def biometric_registration_options(request: Request) -> dict:
    rp_id, _ = webauthn_context(request)
    credentials = biometric_store(rp_id)
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name="Campus Shop",
        user_name="campus-shop-admin",
        user_display_name="Campus Shop",
        authenticator_selection=AuthenticatorSelectionCriteria(
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(credential_id))
            for credential_id in credentials
        ],
    )
    biometric_challenges[f"registration:{rp_id}"] = options.challenge
    return options_to_json_dict(options)


@app.post("/api/biometrie/inscription/verification")
def verify_biometric_registration(request: Request, payload: dict) -> dict[str, bool]:
    rp_id, origin = webauthn_context(request)
    challenge = biometric_challenges.pop(f"registration:{rp_id}", None)
    if challenge is None:
        raise HTTPException(status_code=400, detail="Inscription biométrique expirée")
    try:
        verification = verify_registration_response(
            credential=payload,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            require_user_verification=True,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Empreinte biométrique non vérifiée") from exc
    biometric_store(rp_id)[bytes_to_base64url(verification.credential_id)] = {
        "id": verification.credential_id,
        "public_key": verification.credential_public_key,
        "sign_count": verification.sign_count,
    }
    return {"verified": True}


@app.get("/api/biometrie/approbation/options")
def biometric_approval_options(request: Request) -> dict:
    rp_id, _ = webauthn_context(request)
    credentials = biometric_store(rp_id)
    if not credentials:
        raise HTTPException(status_code=409, detail="Aucune empreinte enregistrée")
    options = generate_authentication_options(
        rp_id=rp_id,
        allow_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(credential_id))
            for credential_id in credentials
        ],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    biometric_challenges[f"authentication:{rp_id}"] = options.challenge
    return options_to_json_dict(options)


@app.post("/api/biometrie/approbation/verification")
def verify_biometric_approval(request: Request, payload: dict) -> dict[str, bool]:
    rp_id, origin = webauthn_context(request)
    challenge = biometric_challenges.pop(f"authentication:{rp_id}", None)
    credential = biometric_store(rp_id).get(str(payload.get("id", "")))
    if challenge is None or credential is None:
        raise HTTPException(status_code=400, detail="Approbation biométrique expirée")
    try:
        verification = verify_authentication_response(
            credential=payload,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=credential["public_key"],
            credential_current_sign_count=credential["sign_count"],
            require_user_verification=True,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Empreinte biométrique non vérifiée") from exc
    credential["sign_count"] = verification.new_sign_count
    return {"verified": True}


def issue_event_ticket(client_id: str) -> str:
    now = time.monotonic()
    recent = [stamp for stamp in ticket_requests.get(client_id, []) if now - stamp < 60]
    if len(recent) >= 12:
        raise HTTPException(status_code=429, detail="Trop de demandes de ticket")
    recent.append(now)
    ticket_requests[client_id] = recent
    ticket = secrets.token_urlsafe(32)
    event_tickets[ticket] = now + 30
    return ticket


@app.post("/api/evenements/ticket")
def event_ticket(request: Request, _: Annotated[str | None, Depends(lambda: None)] = None) -> dict[str, str]:
    client_id = request.client.host if request.client else "unknown"
    return {"ticket": issue_event_ticket(client_id)}


def consume_event_ticket(ticket: str, request: Request) -> None:
    expires = event_tickets.pop(ticket, None)
    if expires is None or time.monotonic() > expires:
        raise HTTPException(status_code=401, detail="Ticket SSE invalide ou expiré")


def sse(event: dict[str, str | None], name: str | None = None) -> str:
    prefix = f"event: {name}\n" if name else ""
    return prefix + f"id: {event['id']}\ndata: {json.dumps(event)}\n\n"


@app.get("/api/evenements")
async def events(request: Request, ticket: str) -> StreamingResponse:
    consume_event_ticket(ticket, request)
    last_id = request.headers.get("Last-Event-ID") or request.query_params.get("last_id")

    async def stream():
        iterator = event_bus.subscribe(last_id)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(iterator.__anext__(), timeout=15)
                    if event is None:
                        yield "event: resync\ndata: {}\n\n"
                    else:
                        yield sse(event.as_dict())
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                except StopAsyncIteration:
                    break
        finally:
            await iterator.aclose()

    return StreamingResponse(stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache, no-store",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    })


@app.get("/api/sync", response_model=SyncPayload | None)
def get_sync_data() -> SyncPayload | None:
    if not SYNC_FILE.exists():
        return None
    try:
        return SyncPayload.model_validate(json.loads(SYNC_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="Données partagées illisibles") from exc


@app.put("/api/sync", response_model=SyncPayload)
async def put_sync_data(payload: SyncPayload) -> SyncPayload:
    previous: SyncPayload | None = get_sync_data()
    temporary = SYNC_FILE.with_suffix(".tmp")
    try:
        temporary.write_text(payload.model_dump_json(), encoding="utf-8")
        temporary.replace(SYNC_FILE)
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Données partagées non enregistrées") from exc
    if previous is not None:
        old_products = {item.get("id") for item in previous.P}
        new_products = {item.get("id") for item in payload.P}
        for product_id in new_products - old_products:
            await event_bus.publish("produit.cree", str(product_id))
        for product_id in old_products - new_products:
            await event_bus.publish("produit.supprime", str(product_id))
        old_sales = {item.get("id") for item in previous.S}
        new_sales = {item.get("id") for item in payload.S}
        for sale_id in new_sales - old_sales:
            await event_bus.publish("vente.creee", str(sale_id))
        if old_sales == new_sales and previous.S != payload.S:
            await event_bus.publish("paiement.ajoute")
        if previous != payload:
            await event_bus.publish("stats.invalidees")
    return payload


@app.post("/api/auth/login", response_model=LoginResponse)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()]) -> LoginResponse:
    username = os.getenv("ADMIN_USER", "admin")
    password = os.getenv("ADMIN_PASSWORD", "change-me")
    if form.username != username or form.password != password:
        raise HTTPException(status_code=401, detail="Nom d'utilisateur ou mot de passe incorrect")
    expires = datetime.now(timezone.utc) + timedelta(minutes=int(os.getenv("JWT_EXPIRE_MINUTES", "480")))
    return LoginResponse(access_token=jwt.encode({"sub": username, "exp": expires}, SECRET, algorithm=ALGORITHM))


@app.get("/api/auth/me")
def me(user: Annotated[str, Depends(current_user)]) -> dict[str, str]:
    return {"nom_utilisateur": user}


@app.get("/api/produits", response_model=list[Product])
def products(_: Annotated[str, Depends(current_user)]) -> list[Product]:
    return PRODUCTS


@app.post("/api/produits", response_model=Product, status_code=201)
def create_product(payload: ProductInput, _: Annotated[str, Depends(current_user)]) -> Product:
    if payload.facilite_paiement and (payload.nb_tranches is None or payload.intervalle_jours not in {7, 14, 30}):
        raise HTTPException(status_code=422, detail="Les paramètres de facilité sont obligatoires")
    if not payload.facilite_paiement and (payload.nb_tranches is not None or payload.intervalle_jours is not None):
        raise HTTPException(status_code=422, detail="Une facilité non autorisée ne peut pas avoir d'échéancier")
    product = Product(id=max((item.id for item in PRODUCTS), default=0) + 1, **payload.model_dump())
    PRODUCTS.append(product)
    return product


@app.delete("/api/produits/{product_id}", status_code=204)
def delete_product(product_id: int, _: Annotated[str, Depends(current_user)]) -> None:
    for index, product in enumerate(PRODUCTS):
        if product.id == product_id:
            PRODUCTS.pop(index)
            return
    raise HTTPException(status_code=404, detail="Produit introuvable")


@app.post("/api/ventes/liens-envoi")
def sending_link(payload: SendingLinkRequest, _: Annotated[str, Depends(current_user)]) -> dict[str, str | None]:
    from datetime import date

    try:
        sale_date = date.fromisoformat(payload.date_vente)
        message = invoice_message(payload.numero_facture, sale_date, payload.client, payload.produit,
                                  payload.quantite, payload.total, payload.paye, payload.reste)
        return {**sending_links(payload.canal, payload.destinataire, message), "message": message}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/fichiers")
async def upload_file(_: Annotated[str, Depends(current_user)], file: UploadFile = File(...)) -> dict[str, str]:
    if file.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=422, detail="Le fichier doit être une image")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="Image limitée à 5 Mo")
    name = f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}.upload"
    (UPLOAD_DIR / name).write_bytes(data)
    return {"id": name}


@app.post("/api/factures")
async def save_invoice(file: UploadFile = File(...)) -> dict[str, str]:
    name = re.sub(r"[^A-Za-z0-9._-]", "-", Path(file.filename or "facture.pdf").name)
    if not name.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Le fichier doit être un PDF")
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="PDF limité à 10 Mo")
    invoice_path = INVOICE_DIR / name
    invoice_path.write_bytes(data)
    invoice_path.chmod(0o664)
    return {"filename": name}
