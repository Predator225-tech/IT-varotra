from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import re
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field, EmailStr

from .services import invoice_message, sending_links


SECRET = os.getenv("JWT_SECRET", "development-secret-change-me")
ALGORITHM = "HS256"
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
INVOICE_DIR = Path(os.getenv("INVOICE_DIR", "invoice"))
INVOICE_DIR.mkdir(parents=True, exist_ok=True)
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

app = FastAPI(title="Campus Shop API", version="1.0.0")
origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


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
