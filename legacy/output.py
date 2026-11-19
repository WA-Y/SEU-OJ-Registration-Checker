# -*- coding: utf-8 -*-
"""
输出模块：将筛选结果输出为 4 组 Excel + 4 组 JSON。

4 个分组（与前端“已通过”栏分类一致）：
  四牌楼校区_大一大二组、四牌楼校区_专业组、九龙湖校区_大一大二组、九龙湖校区_专业组

每组包含“报名成功”的学生信息。
"""
import json
import os

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

from config import OUTPUT_DIR, OUTPUT_GROUPS

# Excel 列定义（顺序）
EXCEL_COLUMNS = [
    ("name", "姓名"),
    ("student_id", "学号"),
    ("nickname", "花名"),
    ("card_id", "一卡通号"),
    ("phone", "手机号"),
    ("qq", "QQ号"),
    ("grade_name", "年级"),
    ("groups", "组别"),
    ("campus", "校区"),
]


def _person_row(person):
    """把报名人 dict 转成一行展示值。"""
    groups = "、".join(person.get("groups", []))
    return [
        person.get("name", ""),
        person.get("student_id", ""),
        person.get("nickname", ""),
        person.get("card_id", ""),
        person.get("phone", ""),
        person.get("qq", ""),
        person.get("grade_name", ""),
        groups,
        person.get("campus", ""),
    ]


def _group_key(group_def):
    return (group_def["newcomer"], group_def["campus"])


def _safe_filename(label):
    """把“四牌楼校区_大一大二组”转成文件名安全形式（保留“_”）。"""
    return label.replace("（", "_").replace("）", "").replace(" ", "_")


def _is_newcomer_group(g):
    """新手组 = 大一组 或 大二组。"""
    return g in ("大一组", "大二组")


def assign_people_to_groups(people):
    """
    把报名成功的人分配到 4 个分组。
    参数 people: 报名人列表（含 groups 组别、campus 校区）。

    规则（与前端 classifyPerson 一致）：
      - 大一组 / 大二组 -> 大一大二组，按校区分四牌楼/九龙湖
      - 专业组 -> 专业组，按校区分四牌楼/九龙湖
      - 校区：含“九龙湖”归九龙湖，否则归四牌楼
      - 一人可能同时报多个组，则出现在多个分组
    """
    buckets = {_group_key(g): [] for g in OUTPUT_GROUPS}

    for p in people:
        groups = p.get("groups", [])
        campus_raw = p.get("campus", "")
        campus = "九龙湖" if ("九龙湖" in str(campus_raw)) else "四牌楼"

        for g in groups:
            if _is_newcomer_group(g):
                newcomer = True
            elif g == "专业组":
                newcomer = False
            else:
                continue
            key = (newcomer, campus)
            if key in buckets:
                buckets[key].append(p)

    return buckets


def write_excel(group_label, people):
    """输出单个分组的 Excel。"""
    wb = Workbook()
    ws = wb.active
    ws.title = group_label

    # 表头
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="4472C4")
    for col_idx, (_, title) in enumerate(EXCEL_COLUMNS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=title)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    # 数据
    for r, person in enumerate(people, start=2):
        row_vals = _person_row(person)
        for col_idx, val in enumerate(row_vals, start=1):
            ws.cell(row=r, column=col_idx, value=val)

    # 列宽自适应（粗略）
    for col_idx, (_, title) in enumerate(EXCEL_COLUMNS, start=1):
        max_len = len(title)
        for person in people:
            val = _person_row(person)[col_idx - 1]
            max_len = max(max_len, len(str(val)))
        ws.column_dimensions[chr(64 + col_idx)].width = min(max_len + 4, 30)

    path = os.path.join(OUTPUT_DIR, f"{_safe_filename(group_label)}.xlsx")
    wb.save(path)
    return path


def write_json(group_label, people):
    """输出单个分组的 JSON。"""
    path = os.path.join(OUTPUT_DIR, f"{_safe_filename(group_label)}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(people, f, ensure_ascii=False, indent=2)
    return path


def export_all(people):
    """
    把报名成功的人按 4 组输出 Excel + JSON。
    参数 people: 报名成功的人列表。
    返回：[(分组label, 人数, excel路径, json路径), ...]
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    buckets = assign_people_to_groups(people)
    result = []
    for g in OUTPUT_GROUPS:
        key = _group_key(g)
        members = buckets.get(key, [])
        excel_path = write_excel(g["label"], members)
        json_path = write_json(g["label"], members)
        result.append({
            "label": g["label"],
            "count": len(members),
            "excel": excel_path,
            "json": json_path,
        })
    return result


if __name__ == "__main__":
    # 简单自测
    demo = [
        {"name": "张三", "student_id": "123", "groups": ["大一组"], "campus": "四牌楼", "grade_name": "大一"},
        {"name": "李四", "student_id": "124", "groups": ["专业组"], "campus": "九龙湖", "grade_name": "大三"},
    ]
    res = export_all(demo)
    for r in res:
        print(r["label"], r["count"])
