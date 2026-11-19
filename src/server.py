# -*- coding: utf-8 -*-
"""
后端 HTTP 服务器：提供 REST API 供前端网页调用，编排整个校对流程。

API：
  GET  /api/config          -> 当前年份、各文件状态
  POST /api/set_year        -> 设置当前年份（body: {year}）
  POST /api/load_register   -> 读取报名表（body: {path}），返回识别结果摘要
  POST /api/fetch_oierdb    -> 爬取 OIerDb 数据
  POST /api/run_match       -> 执行筛选，生成待确认列表
  GET  /api/people          -> 获取当前人员列表（含状态，供前端渲染左右栏）
  POST /api/action          -> 对某个人执行操作（body: {key, action: confirm|reject|undo}）
  POST /api/export          -> 输出 5 组 excel + json
  GET  /                    -> 前端页面

状态机：
  pending（左侧栏）-> confirm（确认报名成功，进右侧栏）/ reject（取消资格）
  confirmed（右侧栏）-> undo（撤销，回左侧栏）
"""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from config import (
    DATA_DIR,
    OUTPUT_DIR,
    WEB_DIR,
    OIERDB_JSON_PATH,
    REGISTER_JSON_PATH,
    MIDDLE_TO_UNIVERSITY_OFFSET,
    GRADE_TOLERANCE,
)
import excel_reader
import oierdb_fetcher
import matcher
import output as output_mod
from state import (
    StateManager, person_key,
    STATUS_PENDING, STATUS_CONFIRMED, STATUS_REJECTED, STATUS_AUTO_PASS,
)


class AppContext:
    """全局应用上下文，保存当前会话状态。"""
    def __init__(self):
        self.year = 2026          # 当前年份
        self.register_people = []  # 报名人列表（识别结果）
        self.oierdb_index = {}    # OIerDb 索引 name -> [初中入学年份]
        self.oierdb_total = 0
        self.matched_people = []  # 筛选后（含 matched/suspect 标记）
        self.state_mgr = StateManager()
        self.state_mgr._load()
        self.register_path = ""   # 报名表路径
        self.lock = threading.Lock()
        self.oierdb_detail_index = None  # name -> [获奖人对象] 详情索引（懒加载）


CTX = AppContext()


def _set_default_statuses(people):
    """
    初始化默认状态：
      - 专业组的人：auto_pass（自动通过）
      - 新手组（大一大二）且 suspect=True：pending（需人工确认）
      - 新手组且 suspect=False（未命中获奖）：auto_pass
      - 其他（既非专业组也非新手组）：pending（默认待确认，安全起见）
    """
    for p in people:
        key = person_key(p)
        if CTX.state_mgr.get(key) is not None:
            continue  # 已有状态，保留
        if matcher.is_professional_group(p) and not matcher.is_newcomer_group(p):
            CTX.state_mgr.set(key, STATUS_AUTO_PASS)
        elif matcher.is_newcomer_group(p):
            if p.get("suspect"):
                CTX.state_mgr.set(key, STATUS_PENDING)
            else:
                CTX.state_mgr.set(key, STATUS_AUTO_PASS)
        else:
            CTX.state_mgr.set(key, STATUS_PENDING)


def _build_people_view():
    """
    构建前端展示用的人员列表，含状态和左右栏归属。
    """
    view = []
    for p in CTX.matched_people:
        key = person_key(p)
        status = CTX.state_mgr.get(key) or STATUS_PENDING
        # 左右栏归属：
        #   左侧栏 = pending（未确认）
        #   右侧栏 = confirmed + auto_pass（已通过/确认）
        #   rejected = 取消资格（不在两侧，但可查）
        side = None
        if status == STATUS_PENDING:
            side = "left"
        elif status in (STATUS_CONFIRMED, STATUS_AUTO_PASS):
            side = "right"
        else:
            side = "rejected"
        view.append({
            "key": key,
            "name": p.get("name", ""),
            "student_id": p.get("student_id", ""),
            "nickname": p.get("nickname", ""),
            "card_id": p.get("card_id", ""),
            "phone": p.get("phone", ""),
            "qq": p.get("qq", ""),
            "grade_name": p.get("grade_name", ""),
            "grade_year": p.get("grade_year"),
            "groups": p.get("groups", []),
            "campus": p.get("campus", ""),
            "row": p.get("row"),
            "matched": p.get("matched", False),
            "suspect": p.get("suspect", False),
            "oier_candidates": p.get("oier_candidates", []),
            "oier_grades": p.get("oier_grades", []),
            "oier_univ_years": p.get("oier_univ_years", []),
            "status": status,
            "passed_groups": CTX.state_mgr.get_record(key).get("passed_groups", []),
            "side": side,
        })
    return view


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, content):
        data = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._serve_index()
        elif path == "/api/config":
            self._api_config()
        elif path == "/api/people":
            self._api_people()
        elif path == "/api/list_files":
            self._api_list_files()
        elif path == "/api/person_detail":
            self._api_person_detail()
        else:
            self._serve_static(path)

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._read_body()
        if path == "/api/set_year":
            self._api_set_year(body)
        elif path == "/api/load_register":
            self._api_load_register(body)
        elif path == "/api/fetch_oierdb":
            self._api_fetch_oierdb(body)
        elif path == "/api/run_match":
            self._api_run_match(body)
        elif path == "/api/action":
            self._api_action(body)
        elif path == "/api/undo":
            self._api_undo(body)
        elif path == "/api/export":
            self._api_export(body)
        elif path == "/api/reset":
            self._api_reset(body)
        else:
            self._send_json({"error": "not found"}, 404)

    # ---- 页面 ----
    def _serve_index(self):
        idx = os.path.join(WEB_DIR, "index.html")
        if os.path.exists(idx):
            with open(idx, "r", encoding="utf-8") as f:
                self._send_html(f.read())
        else:
            self._send_html("<h1>前端页面缺失，请检查 web/index.html</h1>")

    def _serve_static(self, path):
        # 仅允许服务 web 目录下的静态资源，防止路径穿越
        safe = path.lstrip("/")
        if ".." in safe or safe.startswith("/"):
            self._send_json({"error": "forbidden"}, 403)
            return
        filepath = os.path.join(WEB_DIR, safe)
        if not os.path.isfile(filepath):
            self._send_json({"error": "not found"}, 404)
            return
        ext = os.path.splitext(filepath)[1].lower()
        content_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
        }.get(ext, "application/octet-stream")
        with open(filepath, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ---- API ----
    def _api_config(self):
        self._send_json({
            "year": CTX.year,
            "register_path": CTX.register_path,
            "register_loaded": len(CTX.register_people) > 0,
            "register_count": len(CTX.register_people),
            "oierdb_loaded": len(CTX.oierdb_index) > 0,
            "oierdb_total": CTX.oierdb_total,
            "matched_count": len(CTX.matched_people),
        })

    def _resolve_register_path(self, path):
        """
        解析报名表路径。支持：
        1. 绝对路径（直接存在）
        2. 相对文件名（在 data 目录下查找）
        3. 仅文件名（在 data 目录、Downloads、桌面查找）
        返回存在的路径，找不到返回 None。
        """
        path = path.strip().strip('"').strip("'")
        if not path:
            return None
        # 1. 直接存在
        if os.path.isfile(path):
            return path
        # 2. 相对 data 目录
        candidate = os.path.join(DATA_DIR, path)
        if os.path.isfile(candidate):
            return candidate
        # 3. 仅文件名，在常见位置查找
        basename = os.path.basename(path)
        if basename == path:  # 说明只给了文件名
            search_dirs = [
                DATA_DIR,
                os.path.join(os.path.expanduser("~"), "Downloads"),
                os.path.join(os.path.expanduser("~"), "Desktop"),
                os.path.join(os.path.expanduser("~"), "桌面"),
            ]
            for d in search_dirs:
                if os.path.isdir(d):
                    cand = os.path.join(d, basename)
                    if os.path.isfile(cand):
                        return cand
        return None

    def _api_list_files(self):
        """列出 data 目录及常见位置下的 xlsx 报名表候选。"""
        candidates = []
        search_dirs = [
            DATA_DIR,
            os.path.join(os.path.expanduser("~"), "Downloads"),
            os.path.join(os.path.expanduser("~"), "Desktop"),
            os.path.join(os.path.expanduser("~"), "桌面"),
        ]
        seen = set()
        for d in search_dirs:
            if not os.path.isdir(d):
                continue
            try:
                for fn in os.listdir(d):
                    if fn.lower().endswith((".xlsx", ".xls")) and not fn.startswith("~$"):
                        full = os.path.join(d, fn)
                        if full in seen:
                            continue
                        seen.add(full)
                        try:
                            stat = os.stat(full)
                        except OSError:
                            continue
                        candidates.append({
                            "path": full,
                            "name": fn,
                            "size": stat.st_size,
                            "mtime": stat.st_mtime,
                        })
            except OSError:
                continue
        # 按修改时间倒序
        candidates.sort(key=lambda x: x["mtime"], reverse=True)
        self._send_json({"files": candidates, "data_dir": DATA_DIR})

    def _api_load_register(self, body):
        raw_path = body.get("path", "")
        path = self._resolve_register_path(raw_path)
        if not path:
            self._send_json({
                "error": f"文件不存在: {raw_path}。"
                         f"请把报名表放到 data 目录，或直接填完整路径。",
            }, 400)
            return
        try:
            with CTX.lock:
                people = excel_reader.read_register(path, current_year=CTX.year)
                excel_reader.save_register_json(people)
                CTX.register_people = people
                CTX.register_path = path
                CTX.matched_people = []
                # 重置状态
                CTX.state_mgr.reset()
            self._send_json({"ok": True, "count": len(people), "path": path})
        except Exception as e:
            self._send_json({"error": f"识别失败: {e}"}, 500)

    def _api_fetch_oierdb(self, body):
        force = bool(body.get("force", False))
        try:
            with CTX.lock:
                idx, total = oierdb_fetcher.fetch_and_parse(force=force)
                CTX.oierdb_index = idx
                CTX.oierdb_total = total
            self._send_json({"ok": True, "total": total, "names": len(idx)})
        except Exception as e:
            self._send_json({"error": f"爬取失败: {e}"}, 500)

    def _api_run_match(self, body):
        if not CTX.register_people:
            self._send_json({"error": "请先加载报名表"}, 400)
            return
        if not CTX.oierdb_index:
            self._send_json({"error": "请先爬取 OIerDb 数据"}, 400)
            return
        try:
            with CTX.lock:
                matched = matcher.match_people(CTX.register_people, CTX.oierdb_index)
                CTX.matched_people = matched
                _set_default_statuses(matched)
            # 统计
            pending = sum(1 for p in _build_people_view() if p["side"] == "left")
            self._send_json({
                "ok": True,
                "total": len(matched),
                "pending": pending,
            })
        except Exception as e:
            self._send_json({"error": f"筛选失败: {e}"}, 500)

    def _api_people(self):
        view = _build_people_view()
        left = [p for p in view if p["side"] == "left"]
        right = [p for p in view if p["side"] == "right"]
        rejected = [p for p in view if p["side"] == "rejected"]
        self._send_json({
            "left": left,
            "right": right,
            "rejected": rejected,
            "year": CTX.year,
        })

    def _get_detail_index(self):
        """懒加载 OIerDb 完整获奖详情索引。"""
        if CTX.oierdb_detail_index is None:
            with CTX.lock:
                if CTX.oierdb_detail_index is None:
                    CTX.oierdb_detail_index = oierdb_fetcher.ensure_detail_loaded(force=False)
        return CTX.oierdb_detail_index

    def _api_person_detail(self):
        """
        返回某个报名人的 OIerDb 获奖详情（二级界面）。
        参数（query）：key=学号 或 name=姓名
        返回：该人在 OIerDb 的完整获奖记录（按 uid 分组）+ 官网跳转链接，
              并标注哪些同名者与报名年级匹配（可能的本人）。
        """
        from urllib.parse import parse_qs, urlparse as _urlparse
        qs = parse_qs(_urlparse(self.path).query)
        key = (qs.get("key") or [""])[0].strip()
        name = (qs.get("name") or [""])[0].strip()

        # 找到报名人
        person = None
        for p in CTX.matched_people:
            if key and person_key(p) == key:
                person = p
                break
            if name and p.get("name") == name:
                person = p
                break
        if person is None:
            for p in CTX.register_people:
                if key and person_key(p) == key:
                    person = p
                    break
                if name and p.get("name") == name:
                    person = p
                    break
        if person is None:
            self._send_json({"error": "未找到该报名人"}, 404)
            return

        pname = person.get("name", "")
        detail_index = self._get_detail_index()
        oier_people = detail_index.get(pname, [])

        if not oier_people:
            self._send_json({
                "name": pname,
                "student_id": person.get("student_id", ""),
                "nickname": person.get("nickname", ""),
                "card_id": person.get("card_id", ""),
                "phone": person.get("phone", ""),
                "qq": person.get("qq", ""),
                "grade_name": person.get("grade_name", ""),
                "grade_year": person.get("grade_year"),
                "groups": person.get("groups", []),
                "campus": person.get("campus", ""),
                "matched": False,
                "entries": [],
            })
            return

        # 直接根据报名人的大学入学年份，独立判断每个同名者是否"可能本人"，
        # 不依赖 oier_candidates 缓存（这样即使尚未执行筛选，详情也正确）。
        actual_year = person.get("grade_year")

        # 构建获奖详情列表（同名可能多人，按 uid 分组，标注是否匹配）
        entries = []
        for op in oier_people:
            uid = op.get("uid", "")
            grade = op.get("grade")
            univ_year = (grade + MIDDLE_TO_UNIVERSITY_OFFSET) if isinstance(grade, int) else None
            is_match = False
            if actual_year is not None and univ_year is not None:
                is_match = abs(univ_year - actual_year) <= GRADE_TOLERANCE
            entry = {
                "uid": uid,
                "grade": grade,
                "univ_year": univ_year,
                "is_match": is_match,
                "url": oierdb_fetcher.OIER_PROFILE_URL.format(uid=uid),
                "records": op.get("records", []),
            }
            entries.append(entry)

        # 匹配的排前面
        entries.sort(key=lambda e: (not e["is_match"], -(e["grade"] or 0)))

        self._send_json({
            "name": pname,
            "student_id": person.get("student_id", ""),
            "nickname": person.get("nickname", ""),
            "card_id": person.get("card_id", ""),
            "phone": person.get("phone", ""),
            "qq": person.get("qq", ""),
            "grade_name": person.get("grade_name", ""),
            "grade_year": person.get("grade_year"),
            "groups": person.get("groups", []),
            "campus": person.get("campus", ""),
            "matched": True,
            "entries": entries,
        })

    def _api_action(self, body):
        key = body.get("key", "")
        action = body.get("action", "")
        groups = body.get("groups")  # 可选：部分通过时指定的组别列表
        if not key:
            self._send_json({"error": "缺少 key"}, 400)
            return

        prev = CTX.state_mgr.get_record(key)
        prev_status = prev["status"]
        prev_groups = prev["passed_groups"]

        if action == "confirm":
            passed_groups = list(groups) if isinstance(groups, list) else None
            CTX.state_mgr.set(key, STATUS_CONFIRMED, passed_groups=passed_groups)
        elif action == "reject":
            CTX.state_mgr.set(key, STATUS_REJECTED, passed_groups=[])
        elif action == "undo":
            # 撤销确认 -> 回到 pending；草稿箱撤销 -> 恢复之前状态
            CTX.state_mgr.set(key, STATUS_PENDING, passed_groups=[])
        elif action == "restore":
            # 草稿箱撤销恢复：回到 pending
            CTX.state_mgr.set(key, STATUS_PENDING, passed_groups=[])
        else:
            self._send_json({"error": f"未知操作: {action}"}, 400)
            return

        # 记录历史（用于回退）
        CTX.state_mgr.push_history({
            "key": key,
            "action": action,
            "prev_status": prev_status,
            "prev_groups": prev_groups,
        })
        self._send_json({"ok": True})

    def _api_undo(self, body):
        """回退上一次操作。"""
        entry = CTX.state_mgr.pop_history()
        if entry is None:
            self._send_json({"error": "没有可回退的操作"}, 400)
            return
        key = entry["key"]
        prev_status = entry["prev_status"]
        prev_groups = entry["prev_groups"]
        # 恢复之前状态
        if prev_status is None:
            # 之前无状态，恢复到默认（pending）
            CTX.state_mgr.set(key, STATUS_PENDING, passed_groups=[])
        else:
            CTX.state_mgr.set(key, prev_status, passed_groups=prev_groups or [])
        self._send_json({"ok": True, "key": key})

    def _api_export(self, body):
        # 报名成功的人 = confirmed + auto_pass
        view = _build_people_view()
        passed = [p for p in CTX.matched_people
                  if CTX.state_mgr.get(person_key(p)) in (STATUS_CONFIRMED, STATUS_AUTO_PASS)]
        if not passed:
            self._send_json({"error": "没有报名成功的人"}, 400)
            return
        try:
            with CTX.lock:
                results = output_mod.export_all(passed)
            self._send_json({"ok": True, "groups": results})
        except Exception as e:
            self._send_json({"error": f"输出失败: {e}"}, 500)

    def _api_reset(self, body):
        """
        清除当前会话的所有数据（报名表、OIerDb 索引、筛选结果、状态），
        以便加载并处理下一份 Excel 报名表。
        """
        with CTX.lock:
            CTX.register_people = []
            CTX.oierdb_index = {}
            CTX.oierdb_total = 0
            CTX.matched_people = []
            CTX.register_path = ""
            CTX.state_mgr.reset()
            # 详情索引不主动清理（OIerDb 全量数据可复用，跨表格共用）
        self._send_json({"ok": True})


def run_server(host="127.0.0.1", port=8765):
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"服务已启动: http://{host}:{port}")
    return server


if __name__ == "__main__":
    import webbrowser
    import threading
    port = 8765
    server = run_server(port=port)
    threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
