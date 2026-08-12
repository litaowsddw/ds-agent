"""AgentFlow API 服务包。

双导入根统一（双根单例化）。

部署 PYTHONPATH 同时包含 ``/app`` 与 ``/app/apps/api``，因此同一物理模块既
能以 ``apps.api.app.x`` 也能以 ``app.x`` 导入。两条路径并存会让 Python 把
它们视为**不同模块**，导致以下全局单例出现两份实例：
``gateway.llm.llm_gateway``、限流器、Redis 连接池、bundled skills 缓存等。

本模块在包初始化时安装一个 meta-path finder：任何 ``app`` / ``app.*`` 的
导入请求都会被重定向到规范命名空间 ``apps.api.app[.*]``，保证整个进程中
每个物理模块只有一个实例。历史代码可以逐步迁移到规范名，但行为立即统一。
"""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import importlib.util
import sys

_CANONICAL = "apps.api.app"
_LOADED_FLAG = "__agentflow_dualroot_loaded__"


def _canonical_name(fullname: str) -> str:
    """app → apps.api.app；app.x → apps.api.app.x；其余原名返回。"""
    if fullname == "app":
        return _CANONICAL
    if fullname.startswith("app."):
        return f"{_CANONICAL}{fullname[3:]}"
    return fullname


class _CanonicalAppLoader(importlib.abc.Loader):
    """把别名模块（app[.*]）委托给规范模块（apps.api.app[.*]）加载。"""

    def __init__(self, canonical_spec: importlib.machinery.ModuleSpec | None) -> None:
        self._canonical_spec = canonical_spec

    def create_module(self, spec):  # noqa: D102
        # 规范模块已加载时直接复用，import 机制会把别名注册到同一对象。
        canonical_name = _canonical_name(spec.name)
        if canonical_name in sys.modules:
            return sys.modules[canonical_name]
        return None

    def exec_module(self, module) -> None:  # noqa: D102
        canonical_name = _canonical_name(module.__name__)
        canonical = sys.modules.get(canonical_name)

        # create_module 直接返回了已加载的规范模块，无需再执行。
        if canonical is module:
            return
        # 规范模块已加载完成，别名只需指向它。
        if canonical is not None:
            module.__dict__.update(canonical.__dict__)
            return
        if getattr(module, _LOADED_FLAG, False):
            return

        if self._canonical_spec is None or self._canonical_spec.loader is None:
            raise ImportError(f"无法解析规范模块 {canonical_name}")

        spec = self._canonical_spec
        target = importlib.util.module_from_spec(spec)
        setattr(target, _LOADED_FLAG, True)
        sys.modules[canonical_name] = target
        try:
            spec.loader.exec_module(target)
        except BaseException:
            del sys.modules[canonical_name]
            raise
        sys.modules[module.__name__] = target
        module.__dict__.update(target.__dict__)


class _AppRootAliasFinder(importlib.abc.MetaPathFinder):
    """把 ``app[.*]`` 的导入重定向到 ``apps.api.app[.*]``。"""

    def find_spec(self, fullname: str, path=None, target=None):  # noqa: D102
        canonical_name = _canonical_name(fullname)
        if canonical_name == fullname:
            return None  # 规范名或无关模块，走正常解析

        canonical = sys.modules.get(canonical_name)
        if canonical is not None:
            return importlib.machinery.ModuleSpec(
                fullname,
                loader=_CanonicalAppLoader(None),
                origin=getattr(canonical, "__file__", None),
                is_package=hasattr(canonical, "__path__"),
            )

        try:
            canonical_spec = importlib.util.find_spec(canonical_name)
        except (ImportError, AttributeError, ValueError):
            # 规范树不可用（例如只有 apps/api 在 sys.path 上的最小环境），
            # 回退到原生解析，保持与旧双根行为一致而非直接导入失败。
            return None
        if canonical_spec is None:
            return None
        alias_spec = importlib.machinery.ModuleSpec(
            fullname,
            loader=_CanonicalAppLoader(canonical_spec),
            origin=canonical_spec.origin,
            is_package=canonical_spec.submodule_search_locations is not None,
        )
        alias_spec.submodule_search_locations = canonical_spec.submodule_search_locations
        return alias_spec


def _install_root_alias() -> None:
    # 不在 sys.modules 里预置根包别名：根包对象本身没有状态，而且预置
    # 别名会跳过 import 系统为父包设置子包属性的链路（导致
    # `import apps.api.app.x as y` 的 IMPORT_FROM 解析失败）。
    # 子模块单例统一交给上面的 finder 完成。
    if not any(isinstance(finder, _AppRootAliasFinder) for finder in sys.meta_path):
        sys.meta_path.insert(0, _AppRootAliasFinder())


_install_root_alias()
