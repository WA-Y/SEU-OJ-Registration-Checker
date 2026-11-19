# -*- coding: utf-8 -*-
"""
一键启动脚本。

用法：
  命令行运行 `python run.py`。

功能：
  1. 启动本地服务（默认 http://127.0.0.1:8765），托管 web/ 页面
  2. 自动打开浏览器
  3. 页面内点「联网更新数据库」时，由本地服务抓取 OIerDb 最新获奖数据

依赖：仅 Python 标准库，无需安装任何第三方包。
"""
import os
import sys
import threading
import webbrowser

# 确保能 import src 下的模块
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(BASE_DIR, "src")
sys.path.insert(0, SRC_DIR)

PORT = 8765


def main():
    try:
        import local_server
    except ImportError as e:
        print(f"[错误] 无法加载 src/local_server.py：{e}")
        input("按回车退出...")
        return

    try:
        srv = local_server.run_server(port=PORT)
    except OSError as e:
        print(f"[错误] 端口 {PORT} 被占用：{e}")
        print("请关闭占用该端口的程序后重试，或修改 run.py 中的 PORT。")
        input("按回车退出...")
        return

    threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    print("\n========== SEU-OJ 报名核验 v2 ==========")
    print(f"请在浏览器中访问：http://127.0.0.1:{PORT}")
    print("页面功能：报名表核验 / 导出结果 / 台签 / 准考证 / 签到表")
    print("数据更新：页面内点「联网更新数据库」即可拉取 OIerDb 最新名单")
    print("按 Ctrl+C 或关闭此窗口退出。\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出。")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
