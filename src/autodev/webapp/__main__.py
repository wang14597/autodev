# src/autodev/webapp/__main__.py
"""`python -m autodev.webapp` 入口：装配组合根并起 uvicorn。"""

from __future__ import annotations

import logging
import os

import uvicorn

from autodev.webapp.config import build_app_from_env


def main() -> None:
    # 阶段失败日志(engine)默认只会落到 logging 的 lastResort handler——无时间戳。
    # 一个阶段可能跑十几分钟, 事后排查时"几点失败的"是关键信息, 故显式配置格式。
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = build_app_from_env()
    host = os.environ.get("AUTODEV_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("AUTODEV_WEB_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
