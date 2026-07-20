"""Database operations for safe Workflow webhook triggers."""

from __future__ import annotations

from datetime import datetime

from app.models.workflow_trigger import WorkflowWebhookDeliveryModel, WorkflowWebhookTriggerModel
from app.services.db.base import BaseDBService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class WorkflowWebhookTriggerDBService(BaseDBService[WorkflowWebhookTriggerModel]):
    def __init__(self) -> None:
        super().__init__(WorkflowWebhookTriggerModel)

    async def create_trigger(
        self,
        session: AsyncSession,
        *,
        trigger_id: str,
        workflow_id: str,
        version_id: str,
        org_id: str,
        secret_hash: str,
        created_by: str,
    ) -> WorkflowWebhookTriggerModel:
        trigger = WorkflowWebhookTriggerModel(
            trigger_id=trigger_id,
            workflow_id=workflow_id,
            version_id=version_id,
            org_id=org_id,
            secret_hash=secret_hash,
            enabled=True,
            created_by=created_by,
        )
        session.add(trigger)
        await session.flush()
        return trigger

    async def get_by_version(
        self, session: AsyncSession, version_id: str
    ) -> WorkflowWebhookTriggerModel | None:
        result = await session.execute(
            select(WorkflowWebhookTriggerModel).where(
                WorkflowWebhookTriggerModel.version_id == version_id
            )
        )
        return result.scalar_one_or_none()

    async def get_trigger_required(
        self, session: AsyncSession, trigger_id: str
    ) -> WorkflowWebhookTriggerModel:
        return await self.get_by_id_required(session, trigger_id, "trigger_id")

    async def disable_trigger(
        self, session: AsyncSession, *, trigger_id: str, disabled_by: str
    ) -> WorkflowWebhookTriggerModel:
        trigger = await self.get_trigger_required(session, trigger_id)
        if trigger.enabled:
            trigger.enabled = False
            trigger.disabled_by = disabled_by
            trigger.disabled_at = datetime.utcnow()
            await session.flush()
        return trigger

    async def mark_triggered(
        self, session: AsyncSession, trigger: WorkflowWebhookTriggerModel
    ) -> None:
        trigger.last_triggered_at = datetime.utcnow()
        await session.flush()


class WorkflowWebhookDeliveryDBService(BaseDBService[WorkflowWebhookDeliveryModel]):
    def __init__(self) -> None:
        super().__init__(WorkflowWebhookDeliveryModel)

    async def get_by_idempotency_key(
        self, session: AsyncSession, *, trigger_id: str, idempotency_key_hash: str
    ) -> WorkflowWebhookDeliveryModel | None:
        result = await session.execute(
            select(WorkflowWebhookDeliveryModel).where(
                WorkflowWebhookDeliveryModel.trigger_id == trigger_id,
                WorkflowWebhookDeliveryModel.idempotency_key_hash == idempotency_key_hash,
            )
        )
        return result.scalar_one_or_none()

    async def create_delivery(
        self,
        session: AsyncSession,
        *,
        delivery_id: str,
        trigger_id: str,
        run_id: str,
        idempotency_key_hash: str,
        request_size_bytes: int,
    ) -> WorkflowWebhookDeliveryModel:
        delivery = WorkflowWebhookDeliveryModel(
            delivery_id=delivery_id,
            trigger_id=trigger_id,
            run_id=run_id,
            idempotency_key_hash=idempotency_key_hash,
            request_size_bytes=request_size_bytes,
        )
        session.add(delivery)
        await session.flush()
        return delivery


workflow_webhook_trigger_db = WorkflowWebhookTriggerDBService()
workflow_webhook_delivery_db = WorkflowWebhookDeliveryDBService()
