# -*- coding: utf-8 -*-
"""
全局配置：路径、常量、组别/校区定义。
"""
import os

# 项目根目录（本文件位于 src/ 下，根目录是其上一级）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
WEB_DIR = os.path.join(BASE_DIR, "web")

# 数据文件
RAW_TXT_PATH = os.path.join(DATA_DIR, "raw.txt")        # OIerDb 原始数据（下载缓存）
OIERDB_JSON_PATH = os.path.join(DATA_DIR, "oierdb.json")  # 解析后的获奖人 JSON
OIERDB_DETAIL_JSON_PATH = os.path.join(DATA_DIR, "oierdb_detail.json")  # 完整获奖详情（含 records）
CONTESTS_JSON_PATH = os.path.join(DATA_DIR, "contests.json")  # 比赛列表（下标即 contest_id）
SCHOOL_TXT_PATH = os.path.join(DATA_DIR, "school.txt")  # 学校列表（行号即 school_id）
REGISTER_JSON_PATH = os.path.join(DATA_DIR, "register.json")  # 报名表识别结果
STATE_JSON_PATH = os.path.join(DATA_DIR, "state.json")   # 筛选状态（人工确认结果）

# 组别定义（报名表里可能的取值，含多选）
# 新手组 = 大一组 + 大二组（手册里的“新手组”对应现在的低年级组）
GROUP_FRESHMAN = "大一组"
GROUP_SOPHOMORE = "大二组"
GROUP_PROFESSIONAL = "专业组"

# 校区定义
CAMPUS_SIPAILOU = "四牌楼"   # 四牌楼校区
CAMPUS_JIULONGHU = "九龙湖"   # 九龙湖校区

# 输出分组：4 个固定分组（与前端“已通过”栏分类一致）
# 大一大二组 = 大一组 + 大二组 合并；专业组按校区分
OUTPUT_GROUPS = [
    {"newcomer": True,  "campus": CAMPUS_SIPAILOU,   "label": "四牌楼校区_大一大二组"},
    {"newcomer": False, "campus": CAMPUS_SIPAILOU,   "label": "四牌楼校区_专业组"},
    {"newcomer": True,  "campus": CAMPUS_JIULONGHU,  "label": "九龙湖校区_大一大二组"},
    {"newcomer": False, "campus": CAMPUS_JIULONGHU,  "label": "九龙湖校区_专业组"},
]

# OIerDb 数据端点
OIERDB_RESULT_INFO_URL = "https://oier.api.baoshuo.dev/result.info.json"
OIERDB_STATIC_INFO_URL = "https://oier.api.baoshuo.dev/static.info.json"
# result.txt 下载地址模板（{sha} 为 sha512 前 7 位）
# 注意：cos CDN 有反爬（403），优先用 api 源，api 源已验证可用
OIERDB_RESULT_URLS = [
    "https://oier.api.baoshuo.dev/result.{sha}.txt",
    "https://cos-1.cdn.baoshuo.xyz/oier/result.{sha}.txt",
]

# 初中入学年份 -> 大学入学年份 的偏移（初中 3 年 + 高中 3 年 = 6 年）
MIDDLE_TO_UNIVERSITY_OFFSET = 6

# 年级差容差（手册：绝对值差 <= 1 视为可能不合法）
GRADE_TOLERANCE = 1
