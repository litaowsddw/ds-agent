"""异步数据库 CRUD 服务基类。

提供通用的数据库操作方法，所有数据库服务继承此基类。
"""

from datetime import datetime
from typing import Any, TypeVar, Generic, Type

from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base

# ModelType 是 ORM 模型类型变量。
ModelType = TypeVar("ModelType", bound=Base)


class BaseDBService(Generic[ModelType]):
    """数据库服务基类。

    提供通用的 CRUD 操作，子类只需指定 model_class 即可继承使用。
    """

    def __init__(self, model_class: Type[ModelType]) -> None:
        # model_class 是 ORM 模型类。
        self.model_class = model_class

    async def get_by_id(self, session: AsyncSession, id_value: str, id_field: str = None) -> ModelType | None:
        """根据主键读取记录。"""
        if id_field is None:
            # 默认使用第一个主键列
            pk_cols = self.model_class.__table__.primary_key.columns
            id_field = list(pk_cols)[0].name
        stmt = select(self.model_class).where(
            getattr(self.model_class, id_field) == id_value
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_required(self, session: AsyncSession, id_value: str, id_field: str = None) -> ModelType:
        """根据主键读取记录，不存在则抛出 ValueError。"""
        record = await self.get_by_id(session, id_value, id_field)
        if record is None:
            raise ValueError(f"{self.model_class.__name__} 不存在")
        return record

    async def list_all(self, session: AsyncSession, **filters) -> list[ModelType]:
        """列出所有记录，支持过滤。"""
        stmt = select(self.model_class)
        for field, value in filters.items():
            if hasattr(self.model_class, field) and value is not None:
                stmt = stmt.where(getattr(self.model_class, field) == value)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def list_paginated(
        self,
        session: AsyncSession,
        offset: int = 0,
        limit: int = 50,
        **filters,
    ) -> tuple[list[ModelType], int]:
        """分页列出记录，返回 (records, total_count)。"""
        # 计数查询
        count_stmt = select(func.count()).select_from(self.model_class)
        for field, value in filters.items():
            if hasattr(self.model_class, field) and value is not None:
                count_stmt = count_stmt.where(getattr(self.model_class, field) == value)
        count_result = await session.execute(count_stmt)
        total = count_result.scalar() or 0

        # 数据查询
        stmt = select(self.model_class).offset(offset).limit(limit)
        for field, value in filters.items():
            if hasattr(self.model_class, field) and value is not None:
                stmt = stmt.where(getattr(self.model_class, field) == value)
        result = await session.execute(stmt)
        records = list(result.scalars().all())

        return records, total

    async def create(self, session: AsyncSession, **data) -> ModelType:
        """创建记录。"""
        record = self.model_class(**data)
        session.add(record)
        await session.flush()
        return record

    async def update_by_id(self, session: AsyncSession, id_value: str, **data) -> ModelType:
        """根据主键更新记录。"""
        record = await self.get_by_id_required(session, id_value)
        for key, value in data.items():
            if hasattr(record, key) and value is not None:
                setattr(record, key, value)
        await session.flush()
        return record

    async def delete_by_id(self, session: AsyncSession, id_value: str) -> bool:
        """根据主键删除记录。"""
        record = await self.get_by_id(session, id_value)
        if record is None:
            return False
        await session.delete(record)
        await session.flush()
        return True

    async def count(self, session: AsyncSession, **filters) -> int:
        """统计记录数。"""
        stmt = select(func.count()).select_from(self.model_class)
        for field, value in filters.items():
            if hasattr(self.model_class, field) and value is not None:
                stmt = stmt.where(getattr(self.model_class, field) == value)
        result = await session.execute(stmt)
        return result.scalar() or 0

    async def exists(self, session: AsyncSession, **filters) -> bool:
        """检查记录是否存在。"""
        count = await self.count(session, **filters)
        return count > 0
