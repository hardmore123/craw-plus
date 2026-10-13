# 非主线代码归档

这里的代码**不参与**全量抓取，按原目录结构保留，供查阅或后续并入。可运行主线在 `../01_项目代码/`。

（compintel 竞品认证预警线已于 10-12 并入主线：代码 `overseas/compintel/`，命令 `overseas.cli compintel-*`，
数据在主库 `compintel_*` 表，不再在此归档。）

| 目录 | 来源 | 内容 | 为什么没并入主线 |
|---|---|---|---|
| `海外_工具脚本/` | `海外/scripts/`、`海外/` 根目录 | `progress_matrix_report.py`（全站进度矩阵）、`ledger_scan.py`（台账扫描）、`merge_site_summary*.py`（站点汇总合并）、`schema_inventory.py`（schema/adapter 盘点）、`benchmark.py`、`pack.py`（旧打包） | 一次性或面向 `海外` 旧目录结构的工具，路径按 `海外` 写 |
| `工作区根目录_连通性与站点探测/` | 工作区根目录 | 代理/TLS/SNI/HTTP2 连通性诊断（`proxy_*.mjs`、`sni_diag.mjs`、`tcp_check.mjs`）、站点批量可达性检查（`check_sites.mjs`、`final_check*.mjs`、`run_site_check.ps1`）及结果 JSON | Node.js 探测脚本，用于选代理节点和判断反爬类别，结论已写进文档与 skill ops |
| `51服务器部署辅助/` | 工作区根目录 | `_ssh_helper.py`：通过 SSH 在 51 服务器上执行命令 | 运维辅助；凭据已改为环境变量 `DEPLOY_SSH_HOST/USER/PASS`。部署清单见 `06_文档/工作区根目录文档/51服务器*.md` |

未收录：`crawl4ai-main/`（第三方开源库及另一个证书核验项目）、`client-demo/`（Java 客户端示例，另一项目）、
各版本 zip 包（内容已被当前版本覆盖）、调试用 HTML 落盘文件。
