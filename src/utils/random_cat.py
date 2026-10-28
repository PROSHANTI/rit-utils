import logging
import re
from html.parser import HTMLParser
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

logger = logging.getLogger(__name__)
CAT_PAGE = "https://mimimi.ru/random"
FALLBACK_IMAGE = "/static/images/cat-fallback.jpg"


class CatImageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.image: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "meta" and attributes.get("property") == "og:image":
            candidate = attributes.get("content") or ""
            if re.fullmatch(r"/content/[a-zA-Z0-9_-]+\.(?:jpe?g|png|webp)", candidate, re.I):
                self.image = "https://mimimi.ru" + candidate


class CatRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urlsplit(newurl)
        if target.scheme != "https" or target.netloc != "mimimi.ru":
            raise URLError("Unexpected cat service redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class RandomCatService:
    max_page_bytes = 256_000

    def __init__(self) -> None:
        self.opener = build_opener(CatRedirectHandler())

    def image(self) -> dict[str, str]:
        request = Request(CAT_PAGE, headers={"User-Agent": "RIT-UTILS cat preview", "Cache-Control": "no-cache"})
        try:
            with self.opener.open(request, timeout=3) as response:
                content = response.read(self.max_page_bytes + 1)
            if len(content) > self.max_page_bytes:
                raise ValueError("Cat page is too large")
            parser = CatImageParser()
            parser.feed(content.decode("utf-8", errors="replace"))
            if parser.image:
                return {"url": parser.image}
            raise ValueError("Cat image is missing")
        except (OSError, ValueError, URLError):
            logger.warning("Фото котика недоступно; используется локальная фотография")
            return {"url": FALLBACK_IMAGE}
