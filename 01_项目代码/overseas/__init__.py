"""海外电商采集框架（overseas）。

分层：
    scenarios  场景编排（搜索采集 / 型号监控 / 评价增量）
    sites      站点适配插件（自动发现，含声明式抽取 schema）
    extract    声明式抽取引擎（多选择器兜底 + transforms）
    fetchers   抓取层（HttpFetcher / BrowserFetcher + 浏览器复用）
    infra      基础设施（域名级限速 / 反爬识别 / 缓存 / 代理）
    db         存储层（SQLite，价格与评分按时序快照只增不改）

设计取向与 cert_verify 一致：核心只用标准库，Playwright 为可选依赖，
便于在无外网的 Linux 服务器上离线部署。
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
