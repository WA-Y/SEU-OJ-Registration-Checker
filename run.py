# -*- coding: utf-8 -*-
"""
一键启动脚本。

用法：
  命令行运行 `python run.py`（或 `pip install -r requirements.txt` 后运行）。

功能：
  1. 自动检测并安装依赖（openpyxl）
  2. 启动本地服务
  3. 自动打开浏览器
"""
import os
import sys
import subprocess
import webbrowser
import threading

# 确保能 import src 下的模块
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(BASE_DIR, "src")
sys.path.insert(0, SRC_DIR)

PIP_MIRRORS = [
    "https://mirrors.aliyun.com/pypi/simple/",
    "https://pypi.tuna.tsinghua.edu.cn/simple/",
    "https://pypi.org/simple/",
]


def ensure_dependency(module, pkg_name):
    """检查模块是否可用，不可用则尝试安装。"""
    try:
        __import__(module)
        return True
    except ImportError:
        pass
    print(f"[依赖] 未检测到 {pkg_name}，正在安装...")
    for mirror in PIP_MIRRORS:
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", pkg_name, "-i", mirror],
                stdout=subprocess.DEVNULL,
            )
            print(f"[依赖] {pkg_name} 安装成功")
            return True
        except Exception:
            continue
    print(f"[依赖] {pkg_name} 安装失败，请手动执行：pip install {pkg_name}")
    return False


def main():
    # 依赖
    if not ensure_dependency("openpyxl", "openpyxl"):
        input("按回车退出...")
        return

    # 启动服务
    import server
    port = 8765
    try:
        srv = server.run_server(port=port)
    except OSError as e:
        print(f"[错误] 端口 {port} 被占用：{e}")
        print("请关闭占用该端口的程序后重试，或修改 src/server.py 中的端口。")
        input("按回车退出...")
        return

    threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    print("\n========== 校对工具已启动 ==========")
    print(f"请在浏览器中访问：http://127.0.0.1:{port}")
    print("按 Ctrl+C 或关闭此窗口退出。\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出。")


if __name__ == "__main__":
    main()
