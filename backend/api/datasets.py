from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import List, Optional
import json

from ..db.database import get_db
from ..db.models import Dataset, DatasetExample, Project
from ..core.auth import get_current_project

router = APIRouter(dependencies=[Depends(get_current_project)])


class ExampleInput(BaseModel):
    input:    str
    expected: Optional[str] = ""
    criteria: Optional[List[str]] = []
    category: Optional[str] = "general"
    tags:     Optional[List[str]] = []
    metadata: Optional[dict] = {}


class CreateDatasetRequest(BaseModel):
    name:        str
    project:     str          
    description: Optional[str] = ""
    examples:    Optional[List[ExampleInput]] = []


@router.post("", status_code=201)
async def create_or_update_dataset(
    req: CreateDatasetRequest,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Project).where(
            (Project.name == req.project) | (Project.id == req.project)
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, f"Project '{req.project}' not found")

    ds_result = await db.execute(
        select(Dataset).where(
            Dataset.name == req.name,
            Dataset.project_id == project.id
        )
    )
    dataset = ds_result.scalar_one_or_none()

    if not dataset:
        dataset = Dataset(
            project_id  = project.id,
            name        = req.name,
            description = req.description or ""
        )
        db.add(dataset)
        await db.flush()   

    added = 0
    for ex in req.examples:
        example = DatasetExample(
            dataset_id = dataset.id,
            input      = ex.input,
            expected   = ex.expected or "",
            criteria   = ex.criteria or [],
            category   = ex.category or "general",
            tags       = ex.tags or [],
        )
        db.add(example)
        added += 1

    await db.commit()
    await db.refresh(dataset)

    return {
        "dataset_id":    dataset.id,
        "name":          dataset.name,
        "examples_added": added,
        "message":       f"Dataset '{dataset.name}' ready"
    }


@router.get("")
async def list_datasets(project: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    query = select(Dataset)
    if project:
        proj_result = await db.execute(
            select(Project).where(
                (Project.name == project) | (Project.id == project)
            )
        )
        proj = proj_result.scalar_one_or_none()
        if proj:
            query = query.where(Dataset.project_id == proj.id)

    result = await db.execute(query.order_by(Dataset.created_at.desc()))
    datasets = result.scalars().all()

    # Get example counts
    out = []
    for ds in datasets:
        count_result = await db.execute(
            select(func.count()).where(DatasetExample.dataset_id == ds.id)
        )
        count = count_result.scalar() or 0
        out.append({
            "id":            ds.id,
            "name":          ds.name,
            "description":   ds.description,
            "example_count": count,
            "created_at":    ds.created_at.isoformat() if ds.created_at else None
        })

    return {"datasets": out}


@router.get("/{dataset_id}")
async def get_dataset(dataset_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Dataset).where(Dataset.id == dataset_id))
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(404, "Dataset not found")

    examples_result = await db.execute(
        select(DatasetExample).where(DatasetExample.dataset_id == dataset_id)
    )
    examples = examples_result.scalars().all()

    return {
        "id":          dataset.id,
        "name":        dataset.name,
        "description": dataset.description,
        "examples": [
            {
                "id":       e.id,
                "input":    e.input,
                "expected": e.expected,
                "criteria": e.criteria,
                "category": e.category,
            }
            for e in examples
        ]
    }


@router.delete("/{dataset_id}", status_code=204)
async def delete_dataset(dataset_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Dataset).where(Dataset.id == dataset_id))
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(404, "Dataset not found")
    await db.delete(dataset)
    await db.commit()