from app import create_app
from app.config import BASE_DIR

# CW2 DistRes entry point.
app = create_app()

if __name__ == "__main__":
    import os
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    reload_enabled = os.environ.get("DISTRES_RELOAD", "").lower() in {"1", "true", "yes"}
    if reload_enabled:
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=port,
            reload=True,
            reload_dirs=[str(BASE_DIR)],
            app_dir=str(BASE_DIR),
        )
    else:
        uvicorn.run(app, host="0.0.0.0", port=port)
