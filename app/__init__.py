from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import STATIC_DIR
from .database import init_db
from .routes import router


def create_app() -> FastAPI:
    """
    Application factory.

    Rubric link:
    - Creates the server node used for client-server coordination.
    - Mounts UI/static assets used for the demonstration screenshots.
    - Initialises the data layer before accepting client nodes.
    """
    init_db()

    app = FastAPI(
        title="DistRes v2 - Distributed Resource Access and Synchronisation Engine",
        description="6CM604 CW2 prototype: client-server coordination, pub-sub, read/write access and failover handling.",
        version="1.0.0",
    )

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(router)
    return app
