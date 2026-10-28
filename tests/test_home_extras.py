from io import BytesIO
from unittest.mock import MagicMock
from urllib.error import URLError
from urllib.request import Request
from xml.etree import ElementTree

import pytest
from PIL import Image

from src.main import application
from src.utils.random_cat import CAT_PAGE, FALLBACK_IMAGE, CatImageParser, CatRedirectHandler, RandomCatService


def test_login_background_is_available_without_authentication(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.text.count('class="ambient-background"') == 1
    assert "/static/ambient_background.js?v=ambient-1" in response.text
    assert 'type="password"' in response.text
    assert "/static/home.js" not in response.text and 'id="cat-trigger"' not in response.text


@pytest.mark.parametrize("route", ["home", "send_email", "gen_rit_cert", "doctor_form", "remove_bg", "one_alma", "inventory"])
def test_all_tool_pages_share_one_background_without_home_interactions(authenticated_client, route):
    response = authenticated_client.get(f"/{route}")

    assert response.status_code == 200
    assert response.text.count('class="ambient-background"') == 1
    assert response.text.count("/static/css/ambient_background.css?v=ambient-1") == 1
    assert response.text.count("/static/ambient_background.js?v=ambient-1") == 1
    assert all(response.text.count(f'class="dust-layer dust-{layer}"') == 1 for layer in ("far", "middle", "near"))
    if route != "home":
        assert "/static/home.js" not in response.text and 'id="cat-trigger"' not in response.text


def cat_service(content: bytes):
    service = RandomCatService()
    opener = MagicMock()
    opener.open.return_value.__enter__.return_value.read.return_value = content
    service.opener = opener
    return service, opener


def test_home_keeps_six_tools_and_places_heart_over_second_i(authenticated_client, monkeypatch):
    provider = MagicMock()
    monkeypatch.setattr(application.routes.cats, "image", provider)

    page = authenticated_client.get("/home")

    assert page.status_code == 200
    assert page.text.count('class="utility-icon neon-icon" width="72" height="72"') == 6
    assert '>RIT-UT<span class="brand-heart-letter">I<button' in page.text
    assert 'aria-label="Для тебя, любимая"' in page.text and 'id="cat-trigger"' in page.text
    assert 'id="cat-status"' not in page.text and "aleatori.cat" not in page.text
    assert "font-awesome" not in page.text and "cdnjs.cloudflare.com" not in page.text
    assert 'id="cat-photo" width="360" height="270" alt="Котик" hidden' in page.text
    assert 'id="cat-photo" src=' not in page.text
    provider.assert_not_called()


@pytest.mark.parametrize("module,icon", [("one_alma", "one-alma"), ("inventory", "inventory")])
def test_inner_inventory_pages_keep_compact_icons_without_home_extras(authenticated_client, module, icon):
    response = authenticated_client.get(f"/{module}")

    assert response.status_code == 200
    assert f'/static/images/neon/{icon}.svg" width="36" height="36"' in response.text
    assert 'id="love-trigger"' not in response.text and 'id="cat-trigger"' not in response.text


@pytest.mark.parametrize("name", ["mail", "certificate", "doctor-form", "remove-bg", "one-alma", "inventory", "heart", "paw"])
def test_neon_icons_are_local_and_contain_no_external_resources(client, name):
    response = client.get(f"/static/images/neon/{name}.svg")

    root = ElementTree.fromstring(response.content)

    assert response.status_code == 200
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    assert not any(key.lower().startswith("on") or key.endswith("href") for element in root.iter() for key in element.attrib)
    assert all(element.tag.rsplit("}", 1)[-1] not in {"script", "foreignObject", "image"} for element in root.iter())


def test_local_cat_is_a_small_usable_photograph(client):
    response = client.get(FALLBACK_IMAGE)

    with Image.open(BytesIO(response.content)) as image:
        assert image.format == "JPEG" and image.width > 100 and image.height > 100
        image.verify()

    assert response.status_code == 200 and len(response.content) < 100_000


def test_cat_source_extracts_only_the_photo_and_has_bounded_timeout():
    service, opener = cat_service(b'<script>ignored()</script><meta property="og:image" content="/content/123.jpg">')

    result = service.image()

    assert result == {"url": "https://mimimi.ru/content/123.jpg"}
    assert opener.open.call_args.args[0].full_url == CAT_PAGE
    assert opener.open.call_args.kwargs["timeout"] == 3
    opener.open.return_value.__enter__.return_value.read.assert_called_once_with(service.max_page_bytes + 1)


@pytest.mark.parametrize(
    "path", ["https://evil.test/a.jpg", "//evil.test/a.jpg", "/content/../private.jpg", "javascript:alert(1)"]
)
def test_untrusted_remote_image_paths_cannot_escape_the_cat_host(path):
    parser = CatImageParser()

    parser.feed(f'<meta property="og:image" content="{path}">')

    assert parser.image is None


@pytest.mark.parametrize("url", ["http://mimimi.ru/random", "https://evil.test/random", "https://mimimi.ru@evil.test/random"])
def test_cat_service_rejects_redirects_to_other_origins(url):
    handler = CatRedirectHandler()

    with pytest.raises(URLError):
        handler.redirect_request(Request(CAT_PAGE), None, 302, "Found", {}, url)


@pytest.mark.parametrize("failure", [TimeoutError("timeout"), URLError("offline")])
def test_unavailable_cat_service_returns_the_local_photo(failure):
    service, opener = cat_service(b"")
    opener.open.side_effect = failure

    result = service.image()

    assert result == {"url": FALLBACK_IMAGE}


@pytest.mark.parametrize("content", [b"No picture", b"x" * 256_001])
def test_missing_or_oversized_cat_pages_fall_back(content):
    service, _ = cat_service(content)

    result = service.image()

    assert result == {"url": FALLBACK_IMAGE}


def test_cat_endpoint_requires_login_and_does_not_contact_the_source(client, monkeypatch):
    provider = MagicMock(return_value={"url": FALLBACK_IMAGE})
    monkeypatch.setattr(application.routes.cats, "image", provider)

    response = client.get("/home/cat", follow_redirects=False)

    assert response.is_redirect
    provider.assert_not_called()


def test_authenticated_cat_endpoint_returns_no_store_image_url(authenticated_client, monkeypatch):
    provider = MagicMock(return_value={"url": "https://mimimi.ru/content/321.jpg"})
    monkeypatch.setattr(application.routes.cats, "image", provider)

    response = authenticated_client.get("/home/cat")

    assert response.status_code == 200
    assert response.json() == {"url": "https://mimimi.ru/content/321.jpg"}
    assert response.headers["cache-control"] == "no-store"
