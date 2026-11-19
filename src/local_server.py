# -*- coding: utf-8 -*-
"""
本地服务（v2）。

职责只有一个：把 web/ 目录当作静态站点托管，让 `python run.py` 打开就能用。

页面本身是纯前端应用：报名表读取、筛选、导出、台签/准考证/签到表生成全部在浏览器内完成，
不依赖任何服务端接口。获奖数据库是随仓库分发的离线快照（web/data/*.json.gz）。
如需刷新数据，运行 `python src/oierdb_fetcher.py`（见该模块说明）。
"""
import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import config

APP_NAME = "SEU-OJ 报名核验"
APP_VERSION = "2.0"


class Handler(SimpleHTTPRequestHandler):
    server_version = "SEUOJChecker/" + APP_VERSION

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=config.WEB_DIR, **kwargs)

    # ---- 工具方法 ----
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        # 页面与数据都要拿到最新版本，避免本地反复调试时读到缓存
        if self.path in ("/", "/index.html"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    # ---- 路由 ----
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/ping":
            # 仅用于自检「服务是否起来」，页面不依赖它
            return self._json({
                "ok": True, "app": APP_NAME, "version": APP_VERSION,
                "local": True,
            })
        return super().do_GET()

    def log_message(self, fmt, *args):
        # 只记录接口调用，静态资源不刷屏
        if "/api/" in self.path:
            super().log_message(fmt, *args)


def run_server(port=8765, host="127.0.0.1"):
    """创建并返回服务器实例（未启动 serve_forever）。"""
    if not os.path.isdir(config.WEB_DIR):
        raise RuntimeError("找不到 web/ 目录：%s" % config.WEB_DIR)
    return ThreadingHTTPServer((host, port), Handler)
