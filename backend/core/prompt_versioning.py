import hashlib
import logging
from typing import Optional
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


class PromptRegistry:
    """Database-backed prompt version registry."""

    def register(self, project_id, name, content, tags=None,
                 author="api", description="", db: Session = None):
        from ..db.models import PromptVersion

        tags         = tags or []
        content_hash = _hash_content(content)

        existing = db.query(PromptVersion).filter_by(
            project_id=project_id, name=name, content_hash=content_hash
        ).first()
        if existing:
            return existing

        last = (
            db.query(PromptVersion)
            .filter_by(project_id=project_id, name=name)
            .order_by(PromptVersion.version_num.desc())
            .first()
        )
        version_num = (last.version_num + 1) if last else 1
        version_id  = f"{name}:v{version_num}"

        pv = PromptVersion(
            version_id     = version_id,
            name           = name,
            version_num    = version_num,
            project_id     = project_id,
            content        = content,
            content_hash   = content_hash,
            tags           = tags,
            author         = author,
            description    = description,
            parent_version = last.version_id if last else None,
        )
        db.add(pv)
        db.commit()
        db.refresh(pv)
        return pv

    def get(self, project_id, name, version="latest", db: Session = None):
        from ..db.models import PromptVersion

        if version == "latest":
            return (
                db.query(PromptVersion)
                .filter_by(project_id=project_id, name=name)
                .order_by(PromptVersion.version_num.desc())
                .first()
            )
        v_str = version.split(":")[-1].lstrip("v")
        try:
            v_num = int(v_str)
        except ValueError:
            return None
        return db.query(PromptVersion).filter_by(
            project_id=project_id, name=name, version_num=v_num
        ).first()

    def list_versions(self, project_id, name=None, db: Session = None):
        from ..db.models import PromptVersion

        q = db.query(PromptVersion).filter_by(project_id=project_id)
        if name:
            q = q.filter_by(name=name)
        return q.order_by(PromptVersion.name, PromptVersion.version_num).all()

    def compare(self, project_id, name, version_a, version_b="latest",
                db: Session = None):
        va = self.get(project_id, name, version_a, db)
        vb = self.get(project_id, name, version_b, db)

        if not va or not vb:
            return None

        score_a    = va.avg_score or 0.0
        score_b    = vb.avg_score or 0.0
        score_d    = score_b - score_a
        sufficient = min(va.total_traces or 0, vb.total_traces or 0) >= 20

        if not sufficient:
            rec = (
                f"Insufficient data. v{va.version_num} has {va.total_traces or 0} "
                f"traces, v{vb.version_num} has {vb.total_traces or 0}. Need ≥20."
            )
        elif score_d < -0.5:
            rec = f"Regression detected. v{vb.version_num} is {score_d:.1f} lower. Consider rollback."
        elif score_d > 0.5:
            rec = f"Improvement confirmed. v{vb.version_num} is {score_d:.1f} higher. Safe to promote."
        else:
            rec = f"No significant difference (Δ={score_d:.2f})."

        return {
            "version_a":           va.version_id,
            "version_b":           vb.version_id,
            "score_delta":         round(score_d, 2),
            "regression_detected": score_d < -0.5 and sufficient,
            "recommendation":      rec,
            "sufficient_data":     sufficient,
            "a_traces":            va.total_traces or 0,
            "b_traces":            vb.total_traces or 0,
        }

    def update_metrics(self, project_id, name, version,
                       avg_score, pass_rate, total_traces, db=None):
        v = self.get(project_id, name, version, db)
        if v:
            v.avg_score    = avg_score
            v.pass_rate    = pass_rate
            v.total_traces = total_traces
            db.commit()


_registry = PromptRegistry()


def get_registry() -> PromptRegistry:
    return _registry