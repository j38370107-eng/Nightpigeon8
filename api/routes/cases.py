import logging
from fastapi import APIRouter, Request, HTTPException, Query
from bot.core.database import get_pool
from api.routes.auth import get_current_user

log = logging.getLogger("api.cases")

router = APIRouter()


@router.get("/api/guilds/{guild_id}/cases")
async def get_cases(
    guild_id: int,
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    action: str = Query(None),
    user_id: int = Query(None),
):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    pool = await get_pool()
    offset = (page - 1) * per_page

    conditions = ["guild_id=$1", "active=TRUE"]
    params = [guild_id]
    idx = 2

    if action:
        conditions.append(f"action=${idx}")
        params.append(action)
        idx += 1
    if user_id:
        conditions.append(f"user_id=${idx}")
        params.append(user_id)
        idx += 1

    where = " AND ".join(conditions)

    async with pool.acquire() as conn:
        total_row = await conn.fetchrow(f"SELECT COUNT(*) as cnt FROM cases WHERE {where}", *params)
        rows = await conn.fetch(
            f"SELECT * FROM cases WHERE {where} ORDER BY case_number DESC LIMIT ${idx} OFFSET ${idx+1}",
            *params, per_page, offset
        )

    total = total_row["cnt"] if total_row else 0

    cases = []
    for row in rows:
        from datetime import timezone
        created_ts = None
        if row["created_at"]:
            dt = row["created_at"]
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            created_ts = dt.isoformat()
        cases.append({
            "id": row["id"],
            "case_number": row["case_number"],
            "action": row["action"],
            "user_id": str(row["user_id"]),
            "user_tag": row["user_tag"],
            "moderator_id": str(row["moderator_id"]),
            "moderator_tag": row["moderator_tag"],
            "reason": row["reason"],
            "duration": row["duration"],
            "created_at": created_ts,
            "active": row["active"],
        })

    return {
        "cases": cases,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


@router.get("/api/guilds/{guild_id}/cases/{case_id}")
async def get_case(guild_id: int, case_id: int, request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM cases WHERE guild_id=$1 AND case_number=$2",
            guild_id, case_id
        )

    if not row:
        raise HTTPException(status_code=404, detail="Case not found")

    from datetime import timezone
    created_ts = None
    if row["created_at"]:
        dt = row["created_at"]
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        created_ts = dt.isoformat()

    return {
        "id": row["id"],
        "case_number": row["case_number"],
        "action": row["action"],
        "user_id": str(row["user_id"]),
        "user_tag": row["user_tag"],
        "moderator_id": str(row["moderator_id"]),
        "moderator_tag": row["moderator_tag"],
        "reason": row["reason"],
        "duration": row["duration"],
        "created_at": created_ts,
        "active": row["active"],
    }
