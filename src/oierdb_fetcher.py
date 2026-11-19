# -*- coding: utf-8 -*-
"""
OIerDb 获奖数据爬取与解析模块。

流程（对齐手册，但用官方 API 端点，更稳健）：
1. 请求 result.info.json 获取 result.txt 的 sha512 与 size。
2. 从 CDN 下载 result.txt（压缩格式）。
3. 解析 result.txt：每行逗号分隔，字段顺序为
   uid, initials, name, gender, enroll_middle, oierdb_score, ccf_score, ccf_level, records
   其中 name=第2列(index 2)，enroll_middle(初中入学年份)=第4列(index 4)。
4. 仅保留 enroll_middle >= 2014 的（与手册 C++ 程序一致），输出 oierdb.json。

records 字段编码（每条记录用 "/" 分隔，字段用 ":" 分隔）：
   contest_id : school_id : score : rank : province_index : award_level_index [: ems]
   其中 contest_id 对应 contests.json 数组下标，award_level_index 对应 award_levels 数组下标。

本模块额外保存每个获奖人的【完整获奖记录】（比赛名、奖项、排名、分数、年份、uid），
供二级界面展示"该人在 OIerDb 的具体获奖情况"。
"""
import gzip
import json
import os
import urllib.request

from config import (
    DATA_DIR,
    RAW_TXT_PATH,
    OIERDB_JSON_PATH,
    OIERDB_DETAIL_JSON_PATH,
    CONTESTS_JSON_PATH,
    CONTESTS_JSON_PATH_FALLBACK,
    SCHOOL_TXT_PATH,
    WEB_INDEX_GZ,
    WEB_DETAIL_GZ,
    OIERDB_RESULT_INFO_URL,
    OIERDB_RESULT_URLS,
)

USER_AGENT = "Mozilla/5.0 (OIerDb-校对工具)"

# 奖项等级列表（下标即 award_level_index）
AWARD_LEVELS = [
    "金牌", "银牌", "铜牌",
    "一等奖", "二等奖", "三等奖",
    "国际金牌", "国际银牌", "国际铜牌",
    "前5%", "前15%", "前25%",
]

# 省份列表（下标即 province_index）
PROVINCES = [
    "安徽", "北京", "福建", "甘肃", "广东", "广西", "贵州", "海南",
    "河北", "河南", "黑龙江", "湖北", "湖南", "吉林", "江苏", "江西",
    "辽宁", "内蒙古", "山东", "山西", "陕西", "上海", "四川", "天津",
    "新疆", "浙江", "重庆", "宁夏", "云南", "澳门", "香港", "青海",
    "西藏", "台湾",
]

# 选手详情页 URL（uid 即 result.txt 第 1 列）
OIER_PROFILE_URL = "https://oier.baoshuo.dev/oier/{uid}"


def _http_get(url, timeout=60, referer=None):
    """GET 请求，返回 bytes。"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept": "*/*",
    }
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _download_bytes(url, timeout=300, referer=None, progress=None):
    """流式下载并按 2MB 粒度回报进度，避免大文件下载时界面像卡死。"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept": "*/*",
    }
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        try:
            total = int(resp.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            total = 0
        buf = bytearray()
        last_report = 0
        while True:
            chunk = resp.read(256 * 1024)
            if not chunk:
                break
            buf.extend(chunk)
            if progress and len(buf) - last_report >= 2 * 1024 * 1024:
                last_report = len(buf)
                got = len(buf) / 1048576.0
                if total:
                    progress("正在下载 result.txt… %.1f / %.1f MB" % (got, total / 1048576.0))
                else:
                    progress("正在下载 result.txt… %.1f MB" % got)
        return bytes(buf)


def _download_result_txt(progress=None):
    """
    获取 result.txt 的下载地址并下载到本地。
    返回本地文件路径。
    """
    # 1. 获取 result.info.json
    if progress:
        progress("正在获取数据版本…")
    try:
        info = json.loads(_http_get(OIERDB_RESULT_INFO_URL).decode("utf-8"))
    except Exception as e:
        raise RuntimeError(f"无法获取数据信息（{OIERDB_RESULT_INFO_URL}）：{e}。"
                           f"请检查网络能否访问 oier.api.baoshuo.dev")
    sha = info.get("sha512", "")
    if not sha:
        raise RuntimeError("result.info.json 缺少 sha512 字段")
    short_sha = sha[:7]

    # 2. 依次尝试多个下载源
    last_err = None
    for url_tpl in OIERDB_RESULT_URLS:
        url = url_tpl.format(sha=short_sha)
        try:
            # CDN 源加 Referer 以绕过部分反爬
            referer = "https://oier.baoshuo.dev/" if "cdn" in url or "cos" in url else None
            data = _download_bytes(url, timeout=300, referer=referer, progress=progress)
            if not data or len(data) < 1000:
                raise RuntimeError(f"下载内容过小（{len(data)} 字节），疑似被拦截")
            with open(RAW_TXT_PATH, "wb") as f:
                f.write(data)
            print(f"[爬取] 成功下载 result.txt，大小 {len(data)} 字节，来源 {url}")
            return RAW_TXT_PATH
        except Exception as e:
            last_err = e
            print(f"[爬取] 下载失败 {url}: {e}")
    raise RuntimeError(f"所有下载源均失败：{last_err}")


def load_contests():
    """加载比赛列表，返回 dict: contest_id(int) -> {name, type, year, full_score}。"""
    path = CONTESTS_JSON_PATH
    if not os.path.exists(path):
        path = CONTESTS_JSON_PATH_FALLBACK
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        contests = json.load(f)
    result = {}
    for i, c in enumerate(contests):
        result[i] = {
            "name": c.get("name", ""),
            "type": c.get("type", ""),
            "year": c.get("year", None),
            "full_score": c.get("full_score", None),
            "fall_semester": c.get("fall_semester", False),
        }
    return result


def load_schools():
    """加载学校列表，返回 dict: school_id(int) -> 学校名。school.txt 每行一个学校。"""
    if not os.path.exists(SCHOOL_TXT_PATH):
        return {}
    result = {}
    with open(SCHOOL_TXT_PATH, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.rstrip("\n").rstrip("\r")
            if line.strip():
                result[i] = line
    return result


def _parse_record(rec_str, contests, schools):
    """
    解析单条记录字符串 "contest_id:school_id:score:rank:province:award[:ems]"。
    返回 dict；解析失败返回 None。
    """
    parts = rec_str.split(":")
    if len(parts) < 6:
        return None
    try:
        contest_id = int(parts[0])
        school_id = int(parts[1])
        score = parts[2].strip()
        rank = int(parts[3])
        province_idx = int(parts[4])
        award_idx = int(parts[5])
    except (ValueError, IndexError):
        return None

    contest = contests.get(contest_id, {})
    award = AWARD_LEVELS[award_idx] if 0 <= award_idx < len(AWARD_LEVELS) else ""
    province = PROVINCES[province_idx] if 0 <= province_idx < len(PROVINCES) else ""
    school = schools.get(school_id, "")

    return {
        "contest_id": contest_id,
        "contest_name": contest.get("name", ""),
        "contest_type": contest.get("type", ""),
        "year": contest.get("year"),
        "fall_semester": contest.get("fall_semester", False),
        "score": score,
        "rank": rank,
        "award": award,
        "province": province,
        "school": school,
    }


def parse_result_txt(path=None):
    """
    解析 result.txt，返回获奖人列表。
    每个元素：
      {"name": 姓名, "grade": 初中入学年份(int),
       "uid": 用户ID, "records": [获奖记录dict, ...]}
    仅保留 enroll_middle >= 2014 的（与手册一致）。
    """
    path = path or RAW_TXT_PATH
    contests = load_contests()
    schools = load_schools()
    people = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            if line.startswith("#"):
                continue
            parts = line.split(",")
            if len(parts) < 9:
                continue
            uid = parts[0].strip()
            name = parts[2].strip()
            grade_str = parts[4].strip()
            records_str = parts[8].strip()
            if not name:
                continue
            try:
                grade = int(grade_str)
            except ValueError:
                continue
            if grade < 2014:
                continue

            records = []
            if records_str:
                for rec in records_str.split("/"):
                    r = _parse_record(rec, contests, schools)
                    if r:
                        records.append(r)
            # 按年份倒序排列（最新的在前）
            records.sort(key=lambda r: r.get("year") or 0, reverse=True)

            people.append({
                "name": name,
                "grade": grade,
                "uid": uid,
                "records": records,
            })
    return people


def build_oierdb_index(people):
    """
    构建 name -> [同名者列表] 的索引（按 uid 区分，避免同名合并）。

    每个同名者元素：{"uid": str, "grade": 初中入学年份(int)}
    同名可能有多个人（不同 uid），因此值是列表，每个元素是独立的人。
    """
    idx = {}
    for item in people:
        name = item["name"]
        grade = item["grade"]
        uid = item.get("uid", "")
        entry = {"uid": uid, "grade": grade}
        # 去重：同 uid 同 grade 只保留一条
        existing = idx.setdefault(name, [])
        if entry not in existing:
            existing.append(entry)
    # 每个名字下按 grade 排序
    for name in idx:
        idx[name].sort(key=lambda e: e["grade"])
    return idx


def build_name_detail_index(people):
    """
    构建 name -> [完整获奖人对象] 的索引，用于二级界面展示获奖详情。
    同名可能有多个人（不同 uid），因此值是列表。
    """
    idx = {}
    for item in people:
        name = item["name"]
        idx.setdefault(name, []).append(item)
    return idx


def load_oierdb_json():
    """从已保存的 oierdb.json 加载获奖人列表。不存在则返回 None。"""
    if not os.path.exists(OIERDB_JSON_PATH):
        return None
    with open(OIERDB_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_oierdb_detail_json():
    """从 oierdb_detail.json 加载完整获奖详情。不存在则返回 None。"""
    if not os.path.exists(OIERDB_DETAIL_JSON_PATH):
        return None
    with open(OIERDB_DETAIL_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_and_parse(force=False):
    """
    完整流程：下载（如需要）-> 解析 -> 保存 oierdb.json -> 返回索引。

    force=False 时：
      若 data/oierdb.json 已存在，直接加载（避免重复下载）。
      若不存在，则从 OIerDb 官方端点下载 result.txt 并解析。
    """
    people = None
    if not force:
        people = load_oierdb_json()

    if people is None:
        # 需要下载
        if not os.path.exists(RAW_TXT_PATH) or force:
            _download_result_txt()
        people = parse_result_txt()
        if not people:
            raise RuntimeError("解析 result.txt 得到 0 条记录，请检查数据源")
        # 保存完整 JSON（含所有 >=2014 的人）
        with open(OIERDB_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(people, f, ensure_ascii=False)

    return build_oierdb_index(people), len(people)


def ensure_detail_loaded(force=False):
    """
    确保完整获奖详情已加载（供二级界面使用）。
    返回 name -> [获奖人对象列表] 的详情索引。

    说明：oierdb.json 已包含完整详情（含 uid + records），直接复用即可。
    """
    people = None
    if not force:
        people = load_oierdb_json()
    if people is None:
        # 从 raw.txt 重新解析完整详情
        if not os.path.exists(RAW_TXT_PATH):
            _download_result_txt()
        people = parse_result_txt()
        with open(OIERDB_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(people, f, ensure_ascii=False)
    return build_name_detail_index(people)


def _write_gz(path, obj):
    """把对象写成 gzip 压缩的 JSON（前端用 DecompressionStream 直接解压）。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def download_and_parse(progress=None):
    """
    强制下载最新 result.txt 并解析，返回获奖人列表（同时写入 data/oierdb.json）。

    progress: 可选回调 progress(str)，用于把进度推给前端。
    """
    def _p(msg):
        if progress:
            progress(msg)

    _p("正在获取数据版本…")
    _download_result_txt(progress=progress)
    _p("正在解析 result.txt（约 11 万条，需要几十秒）…")
    people = parse_result_txt()
    if not people:
        raise RuntimeError("解析 result.txt 得到 0 条记录，请检查数据源")
    with open(OIERDB_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(people, f, ensure_ascii=False)
    return people


def export_web_data(people=None, progress=None):
    """
    生成前端直接读取的两份快照：
      web/data/oierdb_index.json.gz   name -> [{uid, grade}]
      web/data/oierdb_detail.json.gz  uid  -> [获奖记录]
    返回 (姓名数, uid 数)。
    """
    if people is None:
        people = load_oierdb_json()
    if not people:
        raise RuntimeError("没有可用的 OIerDb 数据，请先执行更新")

    if progress:
        progress("正在生成前端数据快照…")
    index = build_oierdb_index(people)
    detail = {}
    for p in people:
        uid = p.get("uid")
        if uid:
            detail[uid] = p.get("records", [])
    _write_gz(WEB_INDEX_GZ, index)
    _write_gz(WEB_DETAIL_GZ, detail)
    return len(index), len(detail)


if __name__ == "__main__":
    # 手动更新数据：下载 → 解析 → 重建前端快照（覆盖 web/data/*.json.gz）
    print("[1/2] 从 OIerDb 官方接口下载获奖数据（约 13MB）…")
    people = download_and_parse(progress=lambda m: print("     ", m, flush=True))
    print(f"[2/2] 正在生成前端快照…")
    names, uids = export_web_data(people, progress=lambda m: print("     ", m, flush=True))
    print(f"完成：{names} 个姓名 / {uids} 位选手")
    print("快照已写入 web/data/oierdb_index.json.gz、web/data/oierdb_detail.json.gz")
