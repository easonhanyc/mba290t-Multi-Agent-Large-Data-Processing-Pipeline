"""Local preview: the same API plus the static dashboard on one port (Vercel does this in production).

    DATABASE_URL=sqlite:///web/local.db .venv/bin/python web/dev_server.py --port 8765
"""

import argparse
import importlib.util
from pathlib import Path

import uvicorn
from fastapi.staticfiles import StaticFiles

HERE = Path(__file__).resolve().parent


def build_app():
    spec = importlib.util.spec_from_file_location("dashboard_api", HERE / "api" / "index.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.app.mount("/", StaticFiles(directory=HERE / "public", html=True), name="static")
    return mod.app


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    uvicorn.run(build_app(), host="127.0.0.1", port=args.port, log_level="warning")
