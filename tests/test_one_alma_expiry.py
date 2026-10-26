import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from src.main import application
from src.utils.one_alma.expiry import get_expiry_info
from src.utils.one_alma.models import NewProduct
from src.utils.one_alma.repository import InventoryRepository


@pytest.mark.parametrize(
    "expiry,today,expected_end,days,status",
    [
        ("09.2026", date(2026, 10, 1), date(2026, 9, 30), -1, "expired"),
        ("10.2026", date(2026, 10, 31), date(2026, 10, 31), 0, "soon"),
        ("10.2026", date(2026, 11, 1), date(2026, 10, 31), -1, "expired"),
        ("10.2026", date(2026, 10, 23), date(2026, 10, 31), 8, "soon"),
        ("11.2026", date(2026, 10, 23), date(2026, 11, 30), 38, "soon"),
        ("12.2026", date(2026, 10, 23), date(2026, 12, 31), 69, "normal"),
        ("12.2026", date(2026, 10, 30), date(2026, 12, 31), 62, "normal"),
        ("12.2026", date(2026, 10, 31), date(2026, 12, 31), 61, "soon"),
        ("02.2027", date(2026, 12, 31), date(2027, 2, 28), 59, "soon"),
        ("02.2028", date(2027, 12, 31), date(2028, 2, 29), 60, "soon"),
        ("02.2028", date(2028, 2, 29), date(2028, 2, 29), 0, "soon"),
        ("02.2028", date(2028, 3, 1), date(2028, 2, 29), -1, "expired"),
        ("01.2027", date(2026, 11, 30), date(2027, 1, 31), 62, "normal"),
        ("09.2028", date(2026, 10, 23), date(2028, 9, 30), 708, "normal"),
    ],
)
def test_expiry_uses_inclusive_month_end_and_two_calendar_months(expiry, today, expected_end, days, status):
    result = get_expiry_info(expiry, today=today)

    assert result.expires_on == expected_end
    assert result.days_remaining == days
    assert result.status == status


@pytest.mark.parametrize("expiry", ["", "2026-10", "13.2026", "00.2026", "2.2026", "10.26", "10.0000", "10.2026 "])
def test_expiry_rejects_invalid_dates(expiry):
    with pytest.raises(ValueError):
        get_expiry_info(expiry, today=date(2026, 10, 23))


def test_expiry_default_date_uses_moscow_after_utc_midnight_boundary(monkeypatch):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz == ZoneInfo("Europe/Moscow")
            return datetime(2026, 10, 31, 21, 0, tzinfo=ZoneInfo("UTC")).astimezone(tz)

    monkeypatch.setattr("src.utils.one_alma.expiry.datetime", FixedDatetime)

    result = get_expiry_info("10.2026")

    assert result.days_remaining == -1
    assert result.status == "expired"


def test_page_and_sale_response_preserve_expiry_status(authenticated_client, tmp_path, monkeypatch):
    inventory_repository = InventoryRepository(tmp_path / "inventory.sqlite3")
    monkeypatch.setattr(application.routes.one_alma, "repository", inventory_repository)
    match = re.search(r'data-csrf-token="([^"]+)"', authenticated_client.get("/one_alma").text)
    assert match is not None
    csrf = match.group(1)
    monkeypatch.setattr(
        "src.utils.one_alma.one_alma_handler.get_expiry_info", lambda expiry: get_expiry_info(expiry, today=date(2026, 10, 23))
    )
    for position, expiry in [(1001, "09.2026"), (1002, "10.2026"), (1003, "12.2028")]:
        inventory_repository.add_product(
            NewProduct(
                position=position,
                article=f"TEST-{position}",
                name="Крем",
                volume="30 мл",
                expiry=expiry,
                central_bank_price="100",
                wholesale_price="",
                market_price="",
            )
        )
    product = inventory_repository.snapshot().products[-3]

    page = authenticated_client.get("/one_alma")
    response = authenticated_client.post(f"/one_alma/products/{product.id}/showcase", data={"quantity": "1", "csrf_token": csrf})

    assert page.status_code == response.status_code == 200
    for row in page.text.split("<tr data-product-id=")[1:]:
        if "TEST-1001" in row:
            assert 'class="expiry-expired"' in row.split("</tr>")[0]
        if "TEST-1002" in row:
            assert 'class="expiry-soon"' in row.split("</tr>")[0]
        if "TEST-1003" in row:
            assert 'class="expiry-normal"' in row.split("</tr>")[0]
    assert {p["cells"][1]: p["expiry_status"] for p in response.json()["products"] if p["cells"][1].startswith("TEST-")} == {
        "TEST-1001": "expired",
        "TEST-1002": "soon",
        "TEST-1003": "normal",
    }
    assert "31.10.2026 включительно. Осталось: 8 дн." in page.text
    assert "/static/one_alma_expiry.js" in page.text
