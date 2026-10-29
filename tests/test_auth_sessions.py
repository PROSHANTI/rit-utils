import datetime
import re
from http.cookies import SimpleCookie

import pytest

from src.main import application
from src.utils.inventory.models import InventoryItem
from src.utils.inventory.repository import InventoryRepository as WarehouseRepository
from src.utils.one_alma.repository import InventoryRepository as OneAlmaRepository


@pytest.fixture
def session_stores(tmp_path, monkeypatch):
    warehouse = WarehouseRepository(tmp_path / "warehouse.sqlite3")
    one_alma = OneAlmaRepository(tmp_path / "one_alma.sqlite3")
    monkeypatch.setattr(application.routes.inventory, "repository", warehouse)
    monkeypatch.setattr(application.routes.one_alma, "repository", one_alma)
    return warehouse, one_alma


def set_cookie(client, name, value):
    client.cookies.set(name, value, domain="testserver.local", path="/")


def expire_access(client):
    token = application.auth.security.create_access_token(uid="1", expiry=datetime.timedelta(seconds=-10))
    set_cookie(client, application.auth.config.JWT_ACCESS_COOKIE_NAME, token)
    return token


def response_cookies(response):
    cookies = SimpleCookie()
    for header in response.headers.get_list("set-cookie"):
        cookies.load(header)
    return cookies


def csrf_from_page(html: str) -> str:
    match = re.search(r'data-csrf-token="([^"]+)"', html)
    assert match is not None
    return match[1]


@pytest.mark.parametrize("path", ["/home", "/inventory", "/one_alma"])
def test_expired_access_is_renewed_during_original_page_request(authenticated_client, session_stores, path):
    old_access = expire_access(authenticated_client)
    refresh_name = application.auth.config.JWT_REFRESH_COOKIE_NAME
    refresh = authenticated_client.cookies[refresh_name]

    response = authenticated_client.get(path, follow_redirects=False)

    assert response.status_code == 200
    cookies = response_cookies(response)
    access = cookies[application.auth.config.JWT_ACCESS_COOKIE_NAME]
    assert access.value != old_access
    assert access["secure"] and access["httponly"] and access["samesite"] == "lax"
    assert response.headers["cache-control"] == "no-store"
    assert authenticated_client.cookies[refresh_name] == refresh
    assert authenticated_client.get(path, follow_redirects=False).status_code == 200


def test_persistent_refresh_restores_session_when_access_cookie_is_missing(authenticated_client):
    authenticated_client.cookies.delete(application.auth.config.JWT_ACCESS_COOKIE_NAME)

    response = authenticated_client.get("/home", follow_redirects=False)

    assert response.status_code == 200
    assert application.auth.config.JWT_ACCESS_COOKIE_NAME in response_cookies(response)


def test_warehouse_edit_after_access_expiry_is_saved_once(authenticated_client, session_stores):
    warehouse, _ = session_stores
    item_id = warehouse.add(InventoryItem(article="0123", name="Крем", quantity=3, expiry="05.2028"))
    page = authenticated_client.get("/inventory")
    csrf = csrf_from_page(page.text)
    expire_access(authenticated_client)
    data = {"article": "0123", "name": "Новое название", "quantity": 7, "expiry": "05.2028"}

    response = authenticated_client.put(
        f"/inventory/products/{item_id}",
        json=data,
        headers={"Accept": "application/json", "X-CSRF-Token": csrf},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert warehouse.items()[0].name == "Новое название"
    assert warehouse.items()[0].quantity == 7
    assert len(warehouse.items()) == 1


def test_one_alma_quantity_change_after_access_expiry_runs_once(authenticated_client, session_stores):
    _, one_alma = session_stores
    page = authenticated_client.get("/one_alma")
    csrf = csrf_from_page(page.text)
    product = one_alma.snapshot().products[0]
    expire_access(authenticated_client)

    response = authenticated_client.post(
        f"/one_alma/products/{product.id}/showcase",
        data={"quantity": "1", "csrf_token": csrf},
        headers={"Accept": "application/json"},
        follow_redirects=False,
    )

    assert response.status_code == 200
    saved = one_alma.snapshot().products[0]
    assert saved.showcase_quantity == 1
    assert len(saved.units) == len(product.units)
    assert saved.sold_count == product.sold_count


def test_renewed_session_does_not_bypass_csrf(authenticated_client, session_stores):
    warehouse, _ = session_stores
    item_id = warehouse.add(InventoryItem(article="0123", name="Крем", quantity=3))
    expire_access(authenticated_client)

    response = authenticated_client.post(
        f"/inventory/products/{item_id}/quantity",
        json={"delta": 1},
        headers={"Accept": "application/json", "X-CSRF-Token": "wrong"},
        follow_redirects=False,
    )

    assert response.status_code == 403
    assert warehouse.items()[0].quantity == 3


def test_quantity_increment_after_expiry_is_applied_exactly_once(authenticated_client, session_stores):
    warehouse, _ = session_stores
    item_id = warehouse.add(InventoryItem(article="0123", name="Крем", quantity=3))
    page = authenticated_client.get("/inventory")
    csrf = csrf_from_page(page.text)
    expire_access(authenticated_client)

    response = authenticated_client.post(
        f"/inventory/products/{item_id}/quantity",
        json={"delta": 1},
        headers={"Accept": "application/json", "X-CSRF-Token": csrf},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert warehouse.items()[0].quantity == 4


def test_invalid_access_is_not_silently_replaced_using_refresh(authenticated_client):
    set_cookie(authenticated_client, application.auth.config.JWT_ACCESS_COOKIE_NAME, "invalid-token")

    response = authenticated_client.get("/home", headers={"Accept": "application/json"}, follow_redirects=False)

    assert response.status_code == 401
    assert authenticated_client.cookies.get(application.auth.config.JWT_ACCESS_COOKIE_NAME) is None
    assert authenticated_client.cookies.get(application.auth.config.JWT_REFRESH_COOKIE_NAME) is None


@pytest.mark.parametrize("invalid_refresh", ["missing", "expired", "access", "invalid", "revoked", "other-user"])
def test_expired_access_with_invalid_refresh_requires_login(authenticated_client, invalid_refresh):
    refresh_name = application.auth.config.JWT_REFRESH_COOKIE_NAME
    security = application.auth.security
    if invalid_refresh == "missing":
        authenticated_client.cookies.delete(refresh_name)
    elif invalid_refresh == "expired":
        set_cookie(
            authenticated_client, refresh_name, security.create_refresh_token(uid="1", expiry=datetime.timedelta(days=-1))
        )
    elif invalid_refresh == "access":
        set_cookie(authenticated_client, refresh_name, security.create_access_token(uid="1"))
    elif invalid_refresh == "invalid":
        set_cookie(authenticated_client, refresh_name, "not-a-signed-token")
    elif invalid_refresh == "revoked":
        application.auth.revoked_tokens.add(authenticated_client.cookies[refresh_name])
    else:
        set_cookie(authenticated_client, refresh_name, security.create_refresh_token(uid="other-user"))
    expire_access(authenticated_client)

    response = authenticated_client.get("/home", headers={"Accept": "text/plain, application/json"}, follow_redirects=False)

    assert response.status_code == 401
    assert response.json()["detail"]
    assert "location" not in response.headers
    assert authenticated_client.cookies.get(refresh_name) is None
    assert authenticated_client.cookies.get(application.auth.config.JWT_ACCESS_COOKIE_NAME) is None


def test_refresh_json_response_does_not_redirect_through_home(authenticated_client):
    refresh_name = application.auth.config.JWT_REFRESH_COOKIE_NAME
    previous_refresh = authenticated_client.cookies[refresh_name]

    response = authenticated_client.post("/refresh", headers={"Accept": "application/json"}, follow_redirects=False)

    assert response.status_code == 200
    assert response.json() == {"detail": "Сессия продлена."}
    assert "location" not in response.headers
    assert authenticated_client.cookies[refresh_name] == previous_refresh


def test_refresh_endpoint_rejects_access_token_in_refresh_cookie(authenticated_client):
    set_cookie(
        authenticated_client,
        application.auth.config.JWT_REFRESH_COOKIE_NAME,
        application.auth.security.create_access_token(uid="1"),
    )

    response = authenticated_client.post("/refresh", headers={"Accept": "application/json"}, follow_redirects=False)

    assert response.status_code == 401
    assert authenticated_client.cookies.get(application.auth.config.JWT_ACCESS_COOKIE_NAME) is None


def test_logout_after_access_expiry_does_not_restore_access_cookie(authenticated_client):
    expire_access(authenticated_client)
    refresh = authenticated_client.cookies[application.auth.config.JWT_REFRESH_COOKIE_NAME]

    response = authenticated_client.post("/logout", follow_redirects=False)

    assert response.status_code == 303
    assert refresh in application.auth.revoked_tokens
    assert all(cookie["max-age"] == "0" for cookie in response_cookies(response).values())
    assert authenticated_client.cookies.get(application.auth.config.JWT_ACCESS_COOKIE_NAME) is None
    assert authenticated_client.cookies.get(application.auth.config.JWT_REFRESH_COOKIE_NAME) is None
