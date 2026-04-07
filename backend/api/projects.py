import secrets
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from ..core.auth import get_current_project

from ..db.database import get_db
from ..db.models import Project

router = APIRouter()


class CreateProjectRequest(BaseModel):
    name:        str
    description: Optional[str] = ""


@router.post("", status_code=201)
async def create_project(req: CreateProjectRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Project).where(Project.name == req.name))
    if existing.scalar_one_or_none():
        raise HTTPException(400, f"Project '{req.name}' already exists")

    project = Project(
        name        = req.name,
        description = req.description or "",
        api_key     = f"ef_live_{secrets.token_urlsafe(32)}"
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    return {
        "id":      project.id,
        "name":    project.name,
        "api_key": project.api_key,   
        "message": "Save this API key — it won't be shown again"
    }


@router.get("", dependencies=[Depends(get_current_project)])
async def list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    projects = result.scalars().all()
    return {
        "projects": [
            {
                "id":          p.id,
                "name":        p.name,
                "description": p.description,
                "created_at":  p.created_at.isoformat() if p.created_at else None
            }
            for p in projects
        ]
    }


@router.get("/{project_id}", dependencies=[Depends(get_current_project)])
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")

    return {
        "id":          project.id,
        "name":        project.name,
        "description": project.description,
        "created_at":  project.created_at.isoformat() if project.created_at else None
    }


@router.delete("/{project_id}", dependencies=[Depends(get_current_project)])
async def delete_project(project_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    await db.delete(project)
    await db.commit()