"""REST endpoints for direct card/user synchronization between AI Backend and Edge Gateway."""
import logging
import uuid
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

import models
from database import async_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cards", tags=["cards-sync"])


class CardSyncItem(BaseModel):
    card_uid: str
    user_id: Optional[str] = None
    username: Optional[str] = None
    full_name: Optional[str] = None
    role: str = "STUDENT"
    is_active: int = 1


class CardSyncBulkRequest(BaseModel):
    cards: List[CardSyncItem]


def _map_role(role_str: str) -> models.UserRole:
    r = (role_str or "").lower()
    if "lecturer" in r or "giang" in r:
        return models.UserRole.LECTURER
    if "admin" in r:
        return models.UserRole.ADMIN
    return models.UserRole.STUDENT


async def _sync_single_card(item: CardSyncItem, db) -> dict:
    card_uid = item.card_uid.strip()
    role_enum = _map_role(item.role)
    username = item.username or f"user_{card_uid}"
    full_name = item.full_name or username

    try:
        user_uuid = UUID(item.user_id) if item.user_id else uuid.uuid5(uuid.NAMESPACE_DNS, username)
    except (ValueError, TypeError):
        user_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, username)

    # 1. Clear card_uid on any other user currently holding it
    existing_holder = (await db.execute(
        select(models.User).where(models.User.card_uid == card_uid)
    )).scalar_one_or_none()
    if existing_holder and existing_holder.user_id != user_uuid:
        existing_holder.card_uid = None

    # 2. Check if user exists by user_id or username
    existing_user = (await db.execute(
        select(models.User).where(models.User.user_id == user_uuid)
    )).scalar_one_or_none()

    if not existing_user and username:
        existing_user = (await db.execute(
            select(models.User).where(models.User.username == username)
        )).scalar_one_or_none()
        if existing_user:
            user_uuid = existing_user.user_id

    if existing_user:
        existing_user.card_uid = card_uid
        existing_user.role = role_enum
        existing_user.full_name = full_name
        existing_user.username = username
        existing_user.is_active = item.is_active
    else:
        new_user = models.User(
            user_id=user_uuid,
            card_uid=card_uid,
            role=role_enum,
            username=username,
            full_name=full_name,
            is_active=item.is_active,
        )
        db.add(new_user)

    # 3. Update any pending CardRegistrationRequest for this card
    req = (await db.execute(
        select(models.CardRegistrationRequest).where(models.CardRegistrationRequest.card_uid == card_uid)
    )).scalar_one_or_none()
    if req:
        req.status = models.CardRegistrationStatus.APPROVED
        req.assigned_user_id = user_uuid

    return {
        "card_uid": card_uid,
        "user_id": str(user_uuid),
        "username": username,
        "full_name": full_name,
        "role": role_enum.name,
    }


@router.post("/sync")
async def sync_card(req: CardSyncItem):
    """Direct synchronous REST sync for a single card from Cloud/AI Backend to Edge DB."""
    async with async_session() as db:
        try:
            res = await _sync_single_card(req, db)
            await db.commit()
            logger.info("REST Sync: card %s -> user %s (%s)", req.card_uid, res["full_name"], res["role"])
            return {"success": True, "data": res}
        except Exception as e:
            await db.rollback()
            logger.error("REST Sync failed for card %s: %s", req.card_uid, e)
            raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync-bulk")
async def sync_bulk_cards(req: CardSyncBulkRequest):
    """Bulk sync multiple cards to Edge DB in one transaction."""
    results = []
    async with async_session() as db:
        try:
            for item in req.cards:
                res = await _sync_single_card(item, db)
                results.append(res)
            await db.commit()
            logger.info("REST Sync Bulk: synced %d cards to Edge DB", len(results))
            return {"success": True, "count": len(results), "cards": results}
        except Exception as e:
            await db.rollback()
            logger.error("REST Sync Bulk failed: %s", e)
            raise HTTPException(status_code=500, detail=str(e))


@router.get("")
async def list_synced_cards():
    """List all registered cards in Edge Gateway DB."""
    async with async_session() as db:
        rows = (await db.execute(
            select(models.User).where(models.User.card_uid.isnot(None))
        )).scalars().all()
        return [
            {
                "user_id": str(u.user_id),
                "card_uid": u.card_uid,
                "role": u.role.name if hasattr(u.role, "name") else str(u.role),
                "username": u.username,
                "full_name": u.full_name,
                "is_active": u.is_active,
            }
            for u in rows
        ]
