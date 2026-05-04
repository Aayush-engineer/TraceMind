import asyncio
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database  import get_db, get_sync_db
from ..db.models    import Project
from ..core.auth    import get_current_project
from ..core.prompt_versioning import get_registry

router = APIRouter(
    prefix="/api/prompts",
    tags=["prompts"],
    dependencies=[Depends(get_current_project)],
)


class RegisterVersionRequest(BaseModel):
    content:     str
    tags:        List[str] = []
    author:      str       = "api"
    description: str       = ""


@router.post("/{name}/versions", status_code=201)
async def register_version(
    name:    str,
    body:    RegisterVersionRequest,
    project: Project = Depends(get_current_project),
    db:      AsyncSession = Depends(get_db),
):
    if not body.content.strip():
        raise HTTPException(400, "content cannot be empty")

    registry = get_registry()
    loop     = asyncio.get_running_loop()
    sync_db  = get_sync_db()

    try:
        version = await loop.run_in_executor(
            None,
            lambda: registry.register(
                project_id  = project.id,
                name        = name,
                content     = body.content,
                tags        = body.tags,
                author      = body.author,
                description = body.description,
                db          = sync_db,
            )
        )
    finally:
        sync_db.close()

    return {
        "version_id":  version.version_id,
        "name":        version.name,
        "version_num": version.version_num,
        "content":     version.content,
        "tags":        version.tags,
        "author":      version.author,
        "description": version.description,
        "created_at":  version.created_at.isoformat() if version.created_at else None,
    }


@router.get("/{name}/versions")
async def list_versions(
    name:    str,
    project: Project = Depends(get_current_project),
):
    registry = get_registry()
    loop     = asyncio.get_running_loop()
    sync_db  = get_sync_db()

    try:
        versions = await loop.run_in_executor(
            None,
            lambda: registry.list_versions(project.id, name, db=sync_db)
        )
    finally:
        sync_db.close()

    return {
        "versions": [
            {
                "version_id":  v.version_id,
                "name":        v.name,
                "version_num": v.version_num,
                "content":     v.content,
                "tags":        v.tags,
                "author":      v.author,
                "description": v.description,
                "avg_score":   v.avg_score,
                "pass_rate":   v.pass_rate,
                "total_traces":v.total_traces,
                "created_at":  v.created_at.isoformat() if v.created_at else None,
            }
            for v in versions
        ],
        "count": len(versions)
    }


@router.get("/{name}/versions/{version}")
async def get_version(
    name:    str,
    version: str,
    project: Project = Depends(get_current_project),
):
    registry = get_registry()
    loop     = asyncio.get_running_loop()
    sync_db  = get_sync_db()

    try:
        v = await loop.run_in_executor(
            None,
            lambda: registry.get(
                project.id,
                name,
                version,
                db=sync_db,
            )
        )
    finally:
        sync_db.close()

    if not v:
        raise HTTPException(404, f"Version '{version}' not found for prompt '{name}'")

    return {
        "version_id":   v.version_id,
        "name":         v.name,
        "version_num":  v.version_num,
        "content":      v.content,
        "tags":         v.tags,
        "author":       v.author,
        "description":  v.description,
        "avg_score":    v.avg_score,
        "pass_rate":    v.pass_rate,
        "total_traces": v.total_traces,
        "created_at":   v.created_at.isoformat() if v.created_at else None,
    }


@router.get("/{name}/compare")
async def compare_versions(
    name:      str,
    version_a: str,
    version_b: str = "latest",
    project: Project = Depends(get_current_project),
):
    registry = get_registry()
    loop     = asyncio.get_running_loop()
    sync_db  = get_sync_db()

    try:
        comparison = await loop.run_in_executor(
            None,
            lambda: registry.compare(
                project.id,
                name,
                version_a,
                version_b,
                db=sync_db,
            )
        )
    finally:
        sync_db.close()

    if not comparison:
        raise HTTPException(404, "One or both versions not found")

    return comparison.to_dict()