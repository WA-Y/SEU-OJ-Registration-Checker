# -*- coding: utf-8 -*-
"""
报名 Excel 鲁棒识别模块。

目标：从报名 Excel 中提取每个报名人的关键信息，输出标准化 JSON。

鲁棒性设计：
1. 表头模糊匹配：通过关键词识别列（姓名/学号/一卡通号/QQ号/手机号/花名/年级/组别/校区/参赛地点），
   不依赖固定列位置。
2. 组别多列合并：报名表的“组别”可能分散在多列（如早期提交在 K 列、后期在 I 列），
   需要合并处理；多选值（如“大一组, 专业组”）会被拆分。
3. 缺失容错：关键字段缺失时标记为空字符串，不中断。
"""
import json
import re

from openpyxl import load_workbook

from config import (
    DATA_DIR,
    REGISTER_JSON_PATH,
    GROUP_FRESHMAN,
    GROUP_SOPHOMORE,
    GROUP_PROFESSIONAL,
    CAMPUS_SIPAILOU,
    CAMPUS_JIULONGHU,
)


# 表头关键词 -> 字段名（按优先级排列，前面的优先匹配）
HEADER_PATTERNS = [
    ("name",       ["姓名", "名字"]),
    ("student_id", ["学号"]),
    ("nickname",   ["花名"]),
    ("card_id",    ["一卡通"]),
    ("phone",      ["手机", "电话"]),
    ("qq",         ["qq", "QQ", "Q Q"]),
    ("grade",      ["年级"]),
    ("group",      ["组别"]),
    ("campus",     ["校区", "参赛地点", "地点", "赛点"]),
]


def _normalize_header(text):
    """去掉表头里的说明性文字（括号、空格等），便于匹配。"""
    if text is None:
        return ""
    s = str(text).strip()
    # 去掉括号及其内容（如“请选择组别：（比赛分组规则如下图…）（必填）”）
    s = re.sub(r"[（(].*?[)）]", "", s)
    # 去掉“请选择/请填写/请输入/自动/必填/已删除”等词
    s = s.replace("请选择", "").replace("请填写", "").replace("请输入", "")
    s = s.replace("（自动）", "").replace("(自动)", "")
    s = s.replace("（已删除）", "").replace("(已删除)", "")
    s = s.replace("必填", "").replace("（必填）", "").replace("(必填)", "")
    return s.strip()


def _match_field(header):
    """根据表头文本匹配字段名，返回字段名或 None。"""
    norm = _normalize_header(header)
    if not norm:
        return None
    # 精确包含匹配
    for field, keywords in HEADER_PATTERNS:
        for kw in keywords:
            if kw.lower() in norm.lower():
                return field
    return None


def _cell_str(value):
    """把单元格值转成字符串（学号等可能是数字）。"""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    s = str(value).strip()
    return s


# 年级名 -> 相对当前年份的入学偏移（大一=当年入学，大二=前一年，以此类推）
GRADE_OFFSET = {
    "大一": 0,
    "大二": 1,
    "大三": 2,
    "大四": 3,
    "研一": 4,
    "研二": 5,
    "研三": 6,
    "博士": 4,
}


def _parse_grade(grade_str, current_year=None):
    """
    从“大一（26级）”“大二（25级）”等文本中解析：
    返回 (年级名, 入学年份数字) 或 (原串, None)。
    例如 "大一（26级）" -> ("大一", 2026)

    若文本里没有“26级”这种年份，且提供了 current_year，
    则根据年级名推断入学年份（大一 = current_year 入学，大二 = current_year-1，...）。
    """
    s = _cell_str(grade_str)
    if not s:
        return "", None
    # 提取“大一/大二/大三/大四/研一...”等
    grade_name = ""
    m = re.search(r"(大一|大二|大三|大四|研一|研二|研三|博士)", s)
    if m:
        grade_name = m.group(1)
    # 提取年份数字（“26级”里的 26，或“2026级”里的 2026）
    year = None
    m2 = re.search(r"(\d{2,4})\s*级", s)
    if m2:
        y = int(m2.group(1))
        if y < 100:
            year = 2000 + y
        else:
            year = y
    # 兜底：无年份数字时，根据年级名 + 当前年份推断
    if year is None and grade_name and current_year:
        off = GRADE_OFFSET.get(grade_name)
        if off is not None:
            year = current_year - off
    return grade_name, year


def _parse_groups(group_str):
    """
    解析组别字段，返回组别列表。
    支持多选值（“大一组, 专业组”），返回 ["大一组", "专业组"]。
    """
    s = _cell_str(group_str)
    if not s:
        return []
    # 按逗号/顿号/空格/分号分隔
    parts = re.split(r"[,，、;；/\s]+", s)
    groups = []
    for p in parts:
        p = p.strip()
        if GROUP_FRESHMAN in p:
            groups.append(GROUP_FRESHMAN)
        elif GROUP_SOPHOMORE in p:
            groups.append(GROUP_SOPHOMORE)
        elif GROUP_PROFESSIONAL in p:
            groups.append(GROUP_PROFESSIONAL)
    # 去重保序
    seen = []
    for g in groups:
        if g not in seen:
            seen.append(g)
    return seen


def _parse_campus(campus_str):
    """解析校区，返回“四牌楼”/“九龙湖”/“”。"""
    s = _cell_str(campus_str)
    if not s:
        return ""
    if CAMPUS_SIPAILOU in s:
        return CAMPUS_SIPAILOU
    if CAMPUS_JIULONGHU in s:
        return CAMPUS_JIULONGHU
    return s


def read_register(excel_path, current_year=None):
    """
    读取报名 Excel，返回报名人列表。
    每个元素为 dict：
    {
      "name": 姓名, "student_id": 学号, "nickname": 花名,
      "card_id": 一卡通号, "phone": 手机号, "qq": QQ号,
      "grade_name": 年级名(大一/大二...), "grade_year": 入学年份(2026/2025...或None),
      "groups": [组别列表], "campus": 校区, "row": 原行号
    }
    current_year: 当前年份，用于年级无年份数字时兜底推断入学年份。
    """
    wb = load_workbook(excel_path, data_only=True)

    # 多个 sheet 时，自动选择"包含姓名/学号表头且数据行最多"的 sheet，
    # 避免误选到"说明""获奖核验"等辅助表。
    best_ws = None
    best_rows = []
    best_score = -1
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        # 在前 20 行内寻找表头，统计识别出的字段数与数据行数
        header_idx = -1
        header_fields = []
        for i, row in enumerate(rows[:20]):
            fields = [_match_field(c) for c in row]
            if "name" in fields and ("student_id" in fields or "card_id" in fields):
                header_idx = i
                header_fields = fields
                break
        if header_idx < 0:
            continue
        # 数据行数 = 表头之后有姓名的行数
        name_col = None
        for c, f in enumerate(header_fields):
            if f == "name":
                name_col = c
                break
        data_rows = 0
        for row in rows[header_idx + 1:]:
            if name_col is not None and name_col < len(row):
                if _cell_str(row[name_col]):
                    data_rows += 1
        # 评分：数据行数优先（字段丰富度作次要参考）
        score = data_rows * 1000 + len([f for f in header_fields if f])
        if score > best_score:
            best_score = score
            best_ws = ws
            best_rows = rows

    if best_ws is None:
        return []
    ws = best_ws
    rows = best_rows

    # 1. 识别表头
    header_row_idx = None
    col_map = {}  # 字段名 -> 列索引（可能有多个列同字段，如组别）
    col_fields = []  # 每列对应的字段名（含 None）
    for i, row in enumerate(rows[:20]):  # 前 20 行内找表头
        fields = [_match_field(c) for c in row]
        # 表头行应包含“姓名”和“学号”等关键字段
        if "name" in fields and ("student_id" in fields or "card_id" in fields):
            header_row_idx = i
            col_fields = fields
            for col, f in enumerate(fields):
                if f:
                    col_map.setdefault(f, []).append(col)
            break

    if header_row_idx is None:
        # 兜底：第一行作为表头尝试
        header_row_idx = 0
        col_fields = [_match_field(c) for c in rows[0]]
        for col, f in enumerate(col_fields):
            if f:
                col_map.setdefault(f, []).append(col)

    def get_col(row, field):
        """取某行指定字段的值；若该字段有多个列，取第一个非空值。"""
        cols = col_map.get(field, [])
        for c in cols:
            if c < len(row):
                v = _cell_str(row[c])
                if v:
                    return v
        return ""

    def get_group_cols(row):
        """组别可能分散在多列，合并所有组别列的值。"""
        groups = []
        for c in col_map.get("group", []):
            if c < len(row):
                groups.extend(_parse_groups(row[c]))
        # 去重保序
        seen = []
        for g in groups:
            if g not in seen:
                seen.append(g)
        return seen

    people = []
    for idx in range(header_row_idx + 1, len(rows)):
        row = rows[idx]
        name = get_col(row, "name")
        if not name:
            continue  # 无姓名的行跳过
        student_id = get_col(row, "student_id")
        card_id = get_col(row, "card_id")
        qq = get_col(row, "qq")
        phone = get_col(row, "phone")
        nickname = get_col(row, "nickname")
        grade_name, grade_year = _parse_grade(get_col(row, "grade"), current_year)
        groups = get_group_cols(row)
        campus = _parse_campus(get_col(row, "campus"))

        people.append({
            "name": name,
            "student_id": student_id,
            "nickname": nickname,
            "card_id": card_id,
            "phone": phone,
            "qq": qq,
            "grade_name": grade_name,
            "grade_year": grade_year,
            "groups": groups,
            "campus": campus,
            "row": idx + 1,  # 1-based 行号
        })

    return people


def save_register_json(people, path=None):
    """保存识别结果 JSON。"""
    path = path or REGISTER_JSON_PATH
    with open(path, "w", encoding="utf-8") as f:
        json.dump(people, f, ensure_ascii=False, indent=2)
    return path


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        p = sys.argv[1]
    else:
        p = input("请输入报名表 Excel 路径：").strip().strip('"')
    people = read_register(p)
    print(f"识别到 {len(people)} 名报名人")
    for person in people[:10]:
        print(person)
    save_register_json(people)
    print(f"已保存到 {REGISTER_JSON_PATH}")
