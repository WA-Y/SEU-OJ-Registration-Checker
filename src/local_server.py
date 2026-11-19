# -*- coding: utf-8 -*-
"""
本地服务（v2）。

职责很轻：
  1. 把 web/ 目录当作静态站点托管（页面、模板 docx、前端 JS 库、OIerDb 快照）；
  2. 提供可选的「联网更新 OIerDb 数据」接口，浏览器里点一下即可重新抓取。

页面本身是纯前端应用：报名表读取、筛选、导出、台签/准考证/签到表生成都在浏览器内完成。
只有「更新获奖数据库」这一件事浏览器做不到（跨域 + 需要落盘），才落到本地服务。
"""
import json
import os
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import config
import oierdb_fetcher

APP_NAME = "SEU-OJ 报名核验"
APP_VERSION = "2.0"

# 数据更新任务状态（前端轮询 /api/update_status）
_state = {
    "state": "idle",       # idle | running | done | error
    "message": "",
    "names": 0,
    "uids": 0,
    "updated_at": None,
}
_lock = threading.Lock()


def _set_msg(msg):
    _state["message"] = msg


def _start_update():
    """启动后台更新线程；已有任务在跑时返回 False。"""
    with _lock:
        if _state["state"] == "running":
            return False
        _state.update(state="running", message="准备中…", names=0, uids=0)
    threading.Thread(target=_run_update, daemon=True).start()
    return True


def _run_update():
    try:
        people = oierdb_fetcher.download_and_parse(progress=_set_msg)
        names, uids = oierdb_fetcher.export_web_data(people, progress=_set_msg)
        _state.update(
            state="done",
            message="更新完成：%d 个姓名 / %d 位选手" % (names, uids),
            names=names,
            uids=uids,
            updated_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        )
    except Exception as e:                      # 网络异常等，原样反馈给前端
        _state.update(state="error", message="更新失败：%s" % e)


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

    def _plain(self, text, code=200):
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
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
            return self._json({
                "ok": True, "app": APP_NAME, "version": APP_VERSION,
                "local": True, "update_supported": True,
            })
        if path == "/api/update_status":
            return self._json(_state)
        return super().do_GET()

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/update_oierdb":
            started = _start_update()
            return self._json({"started": started, "status": _state})
        return self._json({"error": "not found"}, 404)

    def log_message(self, fmt, *args):
        # 只记录接口调用，静态资源不刷屏
        if "/api/" in self.path:
            super().log_message(fmt, *args)


def run_server(port=8765, host="127.0.0.1"):
    """创建并返回服务器实例（未启动 serve_forever）。"""
    if not os.path.isdir(config.WEB_DIR):
        raise RuntimeError("找不到 web/ 目录：%s" % config.WEB_DIR)
    return ThreadingHTTPServer((host, port), Handler)
