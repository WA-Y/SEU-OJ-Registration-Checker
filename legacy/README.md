# legacy/ —— v1 服务端实现（仅作参考）

这里是项目最初版本的后端：报名表在服务端解析、服务端做 OIerDb 匹配、服务端导出 Excel。

v2 已把同样的逻辑整体搬到浏览器（`web/index.html`），因此这些文件**不参与运行**，保留原因只有两个：

1. 想对照「同一套筛选规则在 Python 里怎么写」；
2. 需要批量在命令行跑一遍核验（无界面）。

## 文件说明

| 文件 | 作用 |
|---|---|
| `server.py` | v1 的 HTTP 后端，提供 `/api/load_register`、`/api/run_match`、`/api/export` 等接口 |
| `excel_reader.py` | 报名表鲁棒识别（多 sheet 扫描、表头模糊匹配、组别多选） |
| `matcher.py` | 筛选逻辑（入学年份推算、同名区分） |
| `state.py` | 待确认 / 已通过 / 草稿箱状态与撤销栈 |
| `output.py` | 按 4 组导出 Excel |

## 如果要跑起来

```bash
pip install openpyxl
```

并且 `config` 与 `legacy` 两个目录都要在 `sys.path` 上（v1 的模块直接从 `src/config.py` 导入路径常量）：

```python
import sys
sys.path.insert(0, "src")
sys.path.insert(0, "legacy")
```

注意：`legacy/server.py` 依赖 v1 的前端页面（调用 `/api/*` 的版本），那份页面已不再随仓库分发。若要完整复活 v1，需要一并恢复对应的前端。
