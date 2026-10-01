import uvicorn

from src.application import WebApplication
from src.auth import auth_service

application = WebApplication(auth_service)
app = application.app

if __name__ == "__main__":
    uvicorn.run("src.main:app", reload=True, host="0.0.0.0", port=8000)
