"""Isolated loopback demo. Uses the production inventory router and its own SQLite DB."""

import os
import secrets
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from src.utils.inventory.inventory_handler import InventoryHandler
from src.utils.inventory.repository import InventoryRepository


class InventoryDemoApplication:
    def __init__(self) -> None:
        root = Path(__file__).resolve().parents[1]
        os.chdir(root)
        self.handler = InventoryHandler(
            InventoryRepository(Path(os.getenv("INVENTORY_DEMO_DB_PATH", str(root / "data" / "inventory-demo.sqlite3"))))
        )
        self.app = FastAPI(docs_url=None, redoc_url=None)
        self.app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
        self.app.mount("/static", StaticFiles(directory="templates"), name="static")
        self.app.include_router(self.handler.router)
        self.app.middleware("http")(self.session)
        self.app.add_api_route("/", self.redirect)
        self.app.add_api_route("/home", self.redirect)
        self.app.add_api_route("/logout", self.redirect, methods=["POST"])

    async def session(self, request: Request, call_next):
        # A local demonstration session; the production router still requires real authentication.
        token = request.cookies.get("INVENTORY_DEMO_SESSION") or secrets.token_urlsafe(32)
        request.state.inventory_demo_session = token
        response = await call_next(request)
        response.set_cookie("INVENTORY_DEMO_SESSION", token, httponly=True, samesite="strict")
        return response

    @staticmethod
    def redirect() -> RedirectResponse:
        return RedirectResponse("/inventory", status_code=303)


application = InventoryDemoApplication()
app = application.app

if __name__ == "__main__":
    port = int(os.getenv("INVENTORY_DEMO_PORT", "8765"))
    print(f"Демо инвентаризации: http://127.0.0.1:{port}/inventory", flush=True)
    uvicorn.run("src.inventory_demo:app", host="127.0.0.1", port=port, reload=True)
