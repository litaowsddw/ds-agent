"""领域模型包。

领域模型只表达业务事实，不直接依赖 FastAPI、数据库或 Celery。
这样做可以让权限、隔离和审计逻辑在 API、Worker、后台 Agent 中复用。
"""
