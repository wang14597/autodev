# src/autodev/webapp/__main__.py
"""`python -m autodev.webapp` 入口：装配组合根并起 uvicorn。"""

from __future__ import annotations

import os

import uvicorn

from autodev.webapp.config import build_app_from_env


def main() -> None:
    app = build_app_from_env()
    host = os.environ.get("AUTODEV_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("AUTODEV_WEB_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
