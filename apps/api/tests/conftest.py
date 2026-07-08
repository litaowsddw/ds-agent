"""API 测试配置。"""

import asyncio
import os
import sys

# 测试环境关闭本地状态文件，确保每次测试都从干净的内存 Store 开始。
os.environ["AGENTFLOW_PERSISTENCE"] = "0"

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
