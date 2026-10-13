"""后端 API 层：零第三方依赖的 REST 服务。

分三层：
    service.py  查询服务：把 db.py 的行数据整理成面向前端的结构
    jobs.py     任务管理：异步跨进程跑采集脚本，串行队列（SQLite 写并发弱）
    server.py   HTTP 路由：标准库 http.server，JSON 响应 + CORS

启动：
    python -m overseas.api.server --host 127.0.0.1 --port 8000
"""
