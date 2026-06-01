"""跨服务集成测试配置。

确保所有集成和压测在干净的内存态下运行，不依赖外部持久化。
"""
import os

os.environ["AGENTFLOW_PERSISTENCE"] = "0"
