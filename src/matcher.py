# -*- coding: utf-8 -*-
"""
筛选逻辑模块。

核心逻辑（对齐手册，并泛化到可配置年份）：

1. OIerDb 中获奖人的 "grade" 是【初中入学年份】(enroll_middle)。
2. 初中入学年份 -> 大学入学年份：大学入学年份 = 初中入学年份 + 6（初中3年+高中3年）。
3. 报名人的大学入学年份从“大一（26级）”解析得到（26 -> 2026）。
4. 若报名人名字在 OIerDb 获奖名单中，且其推算的大学入学年份与报名年份之差 <= 1，
   则标记为“可能获奖 / 需人工确认”。

说明：这是找“报了新手组（大一/大二组）但历史上获过奖的人”，
这些人的奖项等级是否足以剥夺其新手资格，需要人工确认。
"""
from config import MIDDLE_TO_UNIVERSITY_OFFSET, GRADE_TOLERANCE


def middle_to_university_year(middle_year):
    """初中入学年份 -> 大学入学年份。"""
    return middle_year + MIDDLE_TO_UNIVERSITY_OFFSET


def university_year_from_grade_year(grade_year):
    """报名年级的“26级”-> 2026，即大学入学年份。"""
    if grade_year is None:
        return None
    return grade_year


def match_people(register_people, oierdb_index):
    """
    对报名人做筛选，返回结果列表。

    参数：
      register_people: 报名人列表（来自 excel_reader.read_register）
      oierdb_index:   dict, name -> [{"uid", "grade"}, ...]（同名者按 uid 区分）

    返回：列表，每个元素为报名人 dict 加上以下字段：
      "matched": bool，是否命中 OIerDb 获奖名单（存在同名者）
      "suspect": bool，是否"可能获奖/年级可疑"（存在同名者其大学入学年份 ≈ 报名年份）
      "oier_candidates": [同名候选列表]，每个候选：
          {"uid", "grade"(初中入学年份), "univ_year"(推算大学入学年份), "is_match"(是否与报名年份匹配)}
      "oier_grades": [去重后的初中入学年份列表]（兼容旧字段）
      "oier_univ_years": [去重后的推算大学入学年份列表]（兼容旧字段）

    关键：同名不同人时，按 uid 独立判断，而不是把所有年份混在一起。
    """
    results = []
    for p in register_people:
        p = dict(p)  # 复制，避免污染原对象
        name = p.get("name", "")
        p["matched"] = False
        p["suspect"] = False
        p["oier_candidates"] = []
        p["oier_grades"] = []
        p["oier_univ_years"] = []

        if name not in oierdb_index:
            results.append(p)
            continue

        candidates = oierdb_index[name]
        p["matched"] = True

        actual = p.get("grade_year")

        # 对每个同名者（uid）独立判断
        cand_list = []
        match_count = 0
        for c in candidates:
            grade = c["grade"]
            univ_year = middle_to_university_year(grade)
            is_match = False
            if actual is not None and abs(univ_year - actual) <= GRADE_TOLERANCE:
                is_match = True
                match_count += 1
            cand_list.append({
                "uid": c["uid"],
                "grade": grade,
                "univ_year": univ_year,
                "is_match": is_match,
            })
        p["oier_candidates"] = cand_list

        # 去重的年份列表（兼容旧字段，用于界面简要展示）
        p["oier_grades"] = sorted(set(c["grade"] for c in cand_list))
        p["oier_univ_years"] = sorted(set(c["univ_year"] for c in cand_list))

        # 只要存在至少一个同名者的大学入学年份匹配，即为疑似获奖
        if actual is None:
            p["suspect"] = False
        else:
            p["suspect"] = match_count > 0

        results.append(p)

    return results


def is_newcomer_group(person):
    """判断是否为“新手组”（大一组或大二组）。"""
    groups = person.get("groups", [])
    return "大一组" in groups or "大二组" in groups


def is_professional_group(person):
    """判断是否报了专业组。"""
    return "专业组" in person.get("groups", [])
