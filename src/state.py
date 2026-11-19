# -*- coding: utf-8 -*-
"""
状态管理：保存筛选的人工确认结果。

每个报名人有一个状态：
  - "pending": 未确认（在左侧栏，等待人工确认）——仅对“可能获奖”的新手组选手
  - "confirmed": 确认报名成功（通过，进入输出）
  - "rejected": 取消报名资格（不通过，进入草稿箱）
  - "auto_pass": 自动通过（专业组、或新手组未命中获奖名单，无需人工确认）

扩展：
  - 每个报名人可额外记录 "passed_groups"（具体通过的组别列表），
    用于双组别选手部分通过的情况。
  - 操作历史栈（history）用于“回退上一次操作”。
  - 草稿箱 = rejected 状态的人（可撤销恢复）。

状态持久化到 data/state.json，结构：
  {
    "states": { key: {"status": ..., "passed_groups": [...]} },
    "history": [ {key, action, prev} ... ]
  }
"""
import json
import os

from config import STATE_JSON_PATH

# 状态常量
STATUS_PENDING = "pending"       # 未确认（左侧栏）
STATUS_CONFIRMED = "confirmed"   # 确认报名成功（右侧栏）
STATUS_REJECTED = "rejected"     # 取消报名资格（草稿箱）
STATUS_AUTO_PASS = "auto_pass"   # 自动通过


class StateManager:
    def __init__(self, path=None):
        self.path = path or STATE_JSON_PATH
        self.state = {}     # key -> {"status": str, "passed_groups": [...]}
        self.history = []   # 操作历史，用于回退

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # 兼容旧格式：旧版 state 是 key -> "status字符串"
                if isinstance(data, dict) and "states" in data:
                    self.state = data.get("states", {})
                    self.history = data.get("history", [])
                else:
                    self.state = {
                        k: ({"status": v} if isinstance(v, str) else v)
                        for k, v in data.items()
                    }
                    self.history = []
            except Exception:
                self.state = {}
                self.history = []
        else:
            self.state = {}
            self.history = []

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"states": self.state, "history": self.history},
                      f, ensure_ascii=False, indent=2)

    def get(self, key):
        """返回状态字符串（兼容旧接口）。"""
        rec = self.state.get(key)
        if rec is None:
            return None
        if isinstance(rec, dict):
            return rec.get("status")
        return rec

    def get_record(self, key):
        """返回完整记录 dict（含 passed_groups）。"""
        rec = self.state.get(key)
        if rec is None:
            return {"status": None, "passed_groups": []}
        if isinstance(rec, dict):
            return {
                "status": rec.get("status"),
                "passed_groups": rec.get("passed_groups", []),
            }
        return {"status": rec, "passed_groups": []}

    def set(self, key, status, passed_groups=None):
        """
        设置状态。返回旧状态（用于回退栈）。
        """
        old = self.state.get(key)
        old_status = old.get("status") if isinstance(old, dict) else old
        old_groups = old.get("passed_groups", []) if isinstance(old, dict) else []
        rec = {"status": status}
        if passed_groups is not None:
            rec["passed_groups"] = list(passed_groups)
        elif old_groups:
            rec["passed_groups"] = list(old_groups)
        self.state[key] = rec
        self.save()
        return {"status": old_status, "passed_groups": old_groups}

    def push_history(self, entry):
        """记录一次操作（用于回退）。entry: {key, action, prev_status, prev_groups}"""
        self.history.append(entry)
        # 限制历史长度，避免无限增长
        if len(self.history) > 200:
            self.history = self.history[-200:]
        self.save()

    def pop_history(self):
        """弹出最近一次操作。"""
        if not self.history:
            return None
        entry = self.history.pop()
        self.save()
        return entry

    def reset(self):
        self.state = {}
        self.history = []
        if os.path.exists(self.path):
            os.remove(self.path)


def person_key(person):
    """
    报名人的唯一标识。
    优先用学号；学号缺失时用 姓名+一卡通号；再缺失用 姓名+QQ；最后用 姓名+行号。
    """
    sid = person.get("student_id", "")
    if sid:
        return f"sid:{sid}"
    card = person.get("card_id", "")
    if card:
        return f"card:{person.get('name', '')}:{card}"
    qq = person.get("qq", "")
    if qq:
        return f"qq:{person.get('name', '')}:{qq}"
    return f"row:{person.get('name', '')}:{person.get('row', '')}"
