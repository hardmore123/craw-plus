"""竞品情报采集（compintel）：多源认证数据 + 上市预警信号 + LLM 解读。

与电视 spec/retail 业务解耦，独立表族（compintel_*），通过 crawl_run 关联审计。
复用 fetchers.HttpFetcher 与 db.Database。

子模块：
  fcc_crawler        — 从 fccid.io 聚合站抓 FCC 认证记录
  eprel_crawler      — 从 EPREL 官方 API 抓电子显示器/电视能效注册记录
  energystar_crawler — 从 ENERGY STAR Socrata API 抓能效认证(TV/显示器/白电)
  anatel_crawler     — 从 ANATEL 开放数据 ZIP-CSV 抓巴西电信认证
  ic_ised_crawler    — 从 ISED Canada SMS 抓加拿大无线电认证(Spring WebFlow)
  cert_crawler       — TÜV Rheinland(Certipedia) + VDE/CB 安全认证(复用 cert_verify)
  alert              — 9 类上市预警信号识别(含 launch_warning 上市预警)
  compintel_db       — compintel 表族的读写封装
  web_api            — 零依赖可视化看板后端(http.server) + dashboard.html 前端
  llm_analyze        — LLM 解读模块(聚好看内网接口)
  orchestrator       — 抓取编排 + 变化检测
"""
from __future__ import annotations

__all__ = ["fcc_crawler", "eprel_crawler", "energystar_crawler",
           "anatel_crawler", "ic_ised_crawler", "cert_crawler",
           "alert", "compintel_db", "web_api", "llm_analyze", "orchestrator"]
