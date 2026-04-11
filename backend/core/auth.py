import logging
from fastapi            import Depends, HTTPException, Security
from fastapi.security   import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy         import select

from ..db.database import get_db
from ..db.models   import Project

logger  = logging.getLogger(__name__)
bearer  = HTTPBearer(auto_error=False)

security = HTTPBearer(auto_error=False)

async def get_current_project(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> Project:
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Missing Authorization header. Use: Authorization: Bearer ef_live_")
    
    token = credentials.credentials.strip()
    
    if not token.startswith("ef_live_"):
        raise HTTPException(status_code=401, detail="Invalid API key format. Keys must start with ef_live_")
    
    try:
        from sqlalchemy import select
        result = await db.execute(
            select(Project).where(Project.api_key == token)
        )
        project = result.scalar_one_or_none()
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid or expired API key")
    
    if not project:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
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