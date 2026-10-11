from datetime import date

import pytest

from app.services import (gain, invoice_message, normalize_phone, payment_status,
                          schedule, sending_links, total)


def test_total_gain_and_status():
    assert total(3, 25000) == 75000
    assert gain(3, 25000, 18000) == 21000
    assert payment_status(75000, 10000, 10000, 25000) == "en_retard"


def test_schedule_puts_remainder_on_last_installment():
    result = schedule(date(2026, 10, 10), 100000, 3, 14)
    assert [item["montant_prevu"] for item in result] == [33333, 33333, 33334]
    assert result[1]["date_echeance"] == date(2026, 11, 7)


def test_phone_normalization_and_invalid_number():
    assert normalize_phone("034 00 000 00") == "261340000000"
    assert normalize_phone("+261 34 00 000 00") == "261340000000"
    with pytest.raises(ValueError):
        normalize_phone("123")


def test_sending_links_are_encoded():
    message = invoice_message(7, date(2026, 10, 10), "Aina", "Cahier", 2, 6000, 6000, 0)
    links = sending_links("whatsapp", "034 00 000 00", message)
    assert links["whatsapp_url"].startswith("https://wa.me/261340000000?text=")
    assert "%0A" in links["whatsapp_url"]
    with pytest.raises(ValueError):
        sending_links("email", "invalid", message)
