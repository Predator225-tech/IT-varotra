from datetime import date, timedelta
from math import floor
from urllib.parse import quote
import re


def total(quantity: int, sale_price: int) -> int:
    return quantity * sale_price


def gain(quantity: int, sale_price: int, purchase_price: int) -> int:
    return quantity * (sale_price - purchase_price)


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) < 9:
        raise ValueError("Numéro de téléphone invalide")
    return digits if digits.startswith("261") else "261" + digits.removeprefix("0")


def schedule(sale_date: date, remaining: int, installments: int, interval_days: int) -> list[dict[str, object]]:
    base = floor(remaining / installments)
    return [
        {
            "numero_tranche": number,
            "date_echeance": sale_date + timedelta(days=number * interval_days),
            "montant_prevu": remaining - base * (installments - 1) if number == installments else base,
        }
        for number in range(1, installments + 1)
    ]


def payment_status(sale_total: int, paid: int, advance: int, due_amount: int) -> str:
    if paid >= sale_total:
        return "paye"
    if paid < advance + due_amount:
        return "en_retard"
    return "en_cours"


def invoice_message(invoice_number: int, sale_date: date, client: str, product: str,
                    quantity: int, sale_total: int, paid: int, remaining: int,
                    next_due: dict[str, object] | None = None) -> str:
    message = (f"Bonjour {client},\nvoici votre facture n° {invoice_number:04d} du "
               f"{sale_date.strftime('%d/%m/%Y')} :\n{product} ×{quantity}\n"
               f"Total : {sale_total:,} Ar\nDéjà payé : {paid:,} Ar\n"
               f"Reste à payer : {remaining:,} Ar")
    if next_due:
        message += (f"\nProchaine échéance : {next_due['date_echeance'].strftime('%d/%m/%Y')} "
                    f"({next_due['montant_prevu']:,} Ar)")
    return message + "\nMerci pour votre confiance. — Campus Shop"


def sending_links(channel: str, destination: str, message: str) -> dict[str, str | None]:
    if channel == "whatsapp":
        number = normalize_phone(destination)
        return {"whatsapp_url": f"https://wa.me/{number}?text={quote(message)}", "mailto_url": None}
    if channel == "email":
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", destination.strip()):
            raise ValueError("Adresse email invalide")
        subject = quote("Facture Campus Shop")
        return {"whatsapp_url": None, "mailto_url": f"mailto:{destination.strip()}?subject={subject}&body={quote(message)}"}
    if channel != "aucun":
        raise ValueError("Canal d'envoi invalide")
    return {"whatsapp_url": None, "mailto_url": None}
