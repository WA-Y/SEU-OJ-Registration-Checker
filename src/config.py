# -*- coding: utf-8 -*-
"""
全局配置：路径、常量、组别/校区定义。

v2 结构说明：
  - 前端只有一份页面（web/index.html），核验、导出、台签/准考证/签到表全部在浏览器内完成；
  - Python 侧只做两件事：本地静态托管（src/local_server.py）与抓取获奖数据（src/oierdb_fetcher.py）；
  - v1 的服务端实现（服务端读表/匹配/导出）已归档在 legacy/，仅作参考。
"""
import os

# 项目根目录（本文件位于 src/ 下，根目录是其上一级）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")          # 运行时缓存（已 gitignore）
OUTPUT_DIR = os.path.join(BASE_DIR, "output")      # 旧的导出目录（v2 由浏览器直接下载）
WEB_DIR = os.path.join(BASE_DIR, "web")            # 前端页面与静态资源
ASSETS_DIR = os.path.join(BASE_DIR, "assets")      # 随仓库分发的静态元数据
WEB_DATA_DIR = os.path.join(WEB_DIR, "data")       # 前端读取的 OIerDb 快照（gzip JSON）

# 前端数据快照
WEB_INDEX_GZ = os.path.join(WEB_DATA_DIR, "oierdb_index.json.gz")    # 姓名 -> [{uid, grade}]
WEB_DETAIL_GZ = os.path.join(WEB_DATA_DIR, "oierdb_detail.json.gz")  # uid  -> [获奖记录]

# 运行时数据文件
RAW_TXT_PATH = os.path.join(DATA_DIR, "raw.txt")        # OIerDb 原始数据（下载缓存）
OIERDB_JSON_PATH = os.path.join(DATA_DIR, "oierdb.json")  # 解析后的获奖人 JSON
OIERDB_DETAIL_JSON_PATH = os.path.join(DATA_DIR, "oierdb_detail.json")

# 比赛列表：优先用随仓库分发的 assets/contests.json，其次退回 data/ 下的本地缓存
CONTESTS_JSON_PATH = os.path.join(ASSETS_DIR, "contests.json")
CONTESTS_JSON_PATH_FALLBACK = os.path.join(DATA_DIR, "contests.json")
SCHOOL_TXT_PATH = os.path.join(DATA_DIR, "school.txt")   # 学校列表（可选，行号即 school_id）

# 组别定义（报名表里可能的取值，含多选）
GROUP_FRESHMAN = "大一组"
GROUP_SOPHOMORE = "大二组"
GROUP_PROFESSIONAL = "专业组"

# 校区定义
CAMPUS_SIPAILOU = "四牌楼"
CAMPUS_JIULONGHU = "九龙湖"

# 输出分组：4 个固定分组（与前端「已通过」栏分类一致）
OUTPUT_GROUPS = [
    {"newcomer": True,  "campus": CAMPUS_SIPAILOU,  "label": "四牌楼校区_大一大二组"},
    {"newcomer": False, "campus": CAMPUS_SIPAILOU,  "label": "四牌楼校区_专业组"},
    {"newcomer": True,  "campus": CAMPUS_JIULONGHU, "label": "九龙湖校区_大一大二组"},
    {"newcomer": False, "campus": CAMPUS_JIULONGHU, "label": "九龙湖校区_专业组"},
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

# 年级差容差（绝对值差 <= 1 视为可能不合法）
GRADE_TOLERANCE = 1
