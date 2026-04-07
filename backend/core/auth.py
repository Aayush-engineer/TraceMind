import logging
from fastapi            import Depends, HTTPException, Security
from fastapi.security   import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy         import select

from ..db.database import get_db
from ..db.models   import Project

logger  = logging.getLogger(__name__)
bearer  = HTTPBearer(auto_error=False)


async def get_current_project(
    credentials: HTTPAuthorizationCredentials = Security(bearer),
    db:          AsyncSession                 = Depends(get_db)
) -> Project:
    
    if not credentials:
        raise HTTPException(
            status_code = 401,
            detail      = "Missing Authorization header. "
                          "Use: Authorization: Bearer ef_live_<your_key>",
            headers     = {"WWW-Authenticate": "Bearer"}
        )

    api_key = credentials.credentials

    result  = await db.execute(
        select(Project).where(Project.api_key == api_key)
    )
    project = result.scalar_one_or_none()

    if not project:
        logger.warning(f"Invalid API key attempt: {api_key[:12]}...")
        raise HTTPException(
            status_code = 401,
            detail      = "Invalid API key.",
            headers     = {"WWW-Authenticate": "Bearer"}
        )

    return project


async def get_current_project_optional(
    credentials: HTTPAuthorizationCredentials = Security(bearer),
    db:          AsyncSession                 = Depends(get_db)
) -> Project | None:
    if not credentials:
        return None
    try:
        return await get_current_project(credentials, db)
    except HTTPException:
        return None