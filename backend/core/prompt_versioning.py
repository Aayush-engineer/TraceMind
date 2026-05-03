import hashlib
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PromptVersion:
    """A single versioned prompt."""
    version_id:   str              # "support_prompt:v5"
    name:         str              # human name, e.g. "support_prompt"
    version_num:  int              # 1, 2, 3...
    project_id:   str
    content:      str              # full prompt text
    content_hash: str              # sha256 of content (dedup)
    tags:         list[str]        # ["production", "testing", "deprecated"]
    author:       str
    created_at:   float
    description:  str = ""
    parent_version: Optional[str] = None   # version this was branched from

    # Quality metrics (populated after traces accumulate)
    avg_score:    Optional[float] = None
    pass_rate:    Optional[float] = None
    total_traces: int = 0

    @property
    def is_production(self) -> bool:
        return "production" in self.tags

    @property
    def short_hash(self) -> str:
        return self.content_hash[:8]

    def to_dict(self) -> dict:
        return {
            "version_id":   self.version_id,
            "name":         self.name,
            "version_num":  self.version_num,
            "project_id":   self.project_id,
            "content":      self.content,
            "content_hash": self.content_hash,
            "short_hash":   self.short_hash,
            "tags":         self.tags,
            "author":       self.author,
            "created_at":   self.created_at,
            "description":  self.description,
            "is_production": self.is_production,
            "avg_score":    self.avg_score,
            "pass_rate":    self.pass_rate,
            "total_traces": self.total_traces,
        }


@dataclass
class VersionComparison:
    """Quality comparison between two prompt versions."""
    name:               str
    version_a:          PromptVersion
    version_b:          PromptVersion
    score_delta:        float    # positive = B is better
    pass_rate_delta:    float
    regression_detected: bool
    improvement_detected: bool
    recommendation:     str
    a_traces:           int
    b_traces:           int
    sufficient_data:    bool     # True if both versions have >= 20 traces

    @property
    def winner(self) -> Optional[str]:
        if abs(self.score_delta) < 0.3:   # within noise threshold
            return None
        return "B" if self.score_delta > 0 else "A"

    def to_dict(self) -> dict:
        return {
            "name":                self.name,
            "version_a":           self.version_a.version_id,
            "version_b":           self.version_b.version_id,
            "score_delta":         round(self.score_delta, 2),
            "pass_rate_delta":     round(self.pass_rate_delta, 3),
            "regression_detected": self.regression_detected,
            "improvement_detected": self.improvement_detected,
            "recommendation":      self.recommendation,
            "winner":              self.winner,
            "sufficient_data":     self.sufficient_data,
            "a_traces":            self.a_traces,
            "b_traces":            self.b_traces,
        }


def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


class PromptRegistry:
    def __init__(self):
        # {project_id: {name: [PromptVersion, ...]}}
        self._versions: dict[str, dict[str, list[PromptVersion]]] = {}

    def register(
        self,
        project_id:  str,
        name:        str,
        content:     str,
        tags:        list[str] = None,
        author:      str = "unknown",
        description: str = "",
    ) -> PromptVersion:
        tags = tags or []
        content_hash = _hash_content(content)

        # Check for duplicate content
        existing_versions = self._get_versions(project_id, name)
        for v in existing_versions:
            if v.content_hash == content_hash:
                return v   # content unchanged, same version

        version_num = len(existing_versions) + 1
        version_id  = f"{name}:v{version_num}"

        pv = PromptVersion(
            version_id   = version_id,
            name         = name,
            version_num  = version_num,
            project_id   = project_id,
            content      = content,
            content_hash = content_hash,
            tags         = tags,
            author       = author,
            created_at   = time.time(),
            description  = description,
            parent_version = (
                existing_versions[-1].version_id
                if existing_versions else None
            ),
        )

        if project_id not in self._versions:
            self._versions[project_id] = {}
        if name not in self._versions[project_id]:
            self._versions[project_id][name] = []

        self._versions[project_id][name].append(pv)
        return pv

    def get(
        self,
        project_id: str,
        name:       str,
        version:    str = "latest",
    ) -> Optional[PromptVersion]:
        """Get a specific version. 'latest' returns the most recent."""
        versions = self._get_versions(project_id, name)
        if not versions:
            return None
        if version == "latest":
            return versions[-1]
        # Find by version string like "v3" or full "prompt_name:v3"
        v_str = version.split(":")[-1]   # handle both formats
        for v in versions:
            if f"v{v.version_num}" == v_str:
                return v
        return None

    def list_versions(
        self,
        project_id: str,
        name:       Optional[str] = None,
    ) -> list[PromptVersion]:
        """List all versions for a project, optionally filtered by name."""
        if project_id not in self._versions:
            return []
        if name:
            return self._get_versions(project_id, name)
        return [
            v
            for versions in self._versions[project_id].values()
            for v in versions
        ]

    def compare(
        self,
        project_id: str,
        name:       str,
        version_a:  str,
        version_b:  str = "latest",
    ) -> Optional[VersionComparison]:
        """Compare quality metrics between two versions."""
        va = self.get(project_id, name, version_a)
        vb = self.get(project_id, name, version_b)

        if not va or not vb:
            return None

        score_a    = va.avg_score    or 0.0
        score_b    = vb.avg_score    or 0.0
        pr_a       = va.pass_rate    or 0.0
        pr_b       = vb.pass_rate    or 0.0
        score_d    = score_b - score_a
        pr_d       = pr_b - pr_a
        sufficient = min(va.total_traces, vb.total_traces) >= 20

        regression  = score_d < -0.5 and sufficient
        improvement = score_d > 0.5  and sufficient

        if not sufficient:
            rec = (
                f"Insufficient data — v{va.version_num} has {va.total_traces} "
                f"traces, v{vb.version_num} has {vb.total_traces}. "
                f"Need at least 20 per version for reliable comparison."
            )
        elif regression:
            rec = (
                f"Regression detected. v{vb.version_num} scores {score_d:.1f} "
                f"lower than v{va.version_num}. "
                f"Consider rolling back to v{va.version_num}."
            )
        elif improvement:
            rec = (
                f"Improvement confirmed. v{vb.version_num} scores {score_d:.1f} "
                f"higher than v{va.version_num}. Safe to promote to production."
            )
        else:
            rec = (
                f"No significant difference (Δ={score_d:.2f}). "
                f"Both versions perform similarly."
            )

        return VersionComparison(
            name               = name,
            version_a          = va,
            version_b          = vb,
            score_delta        = round(score_d, 3),
            pass_rate_delta    = round(pr_d, 3),
            regression_detected  = regression,
            improvement_detected = improvement,
            recommendation     = rec,
            a_traces           = va.total_traces,
            b_traces           = vb.total_traces,
            sufficient_data    = sufficient,
        )

    def tag_as_production(
        self,
        project_id: str,
        name:       str,
        version:    str,
    ) -> Optional[PromptVersion]:
        """Mark a version as production, remove tag from others."""
        versions = self._get_versions(project_id, name)
        target   = None

        for v in versions:
            if f"v{v.version_num}" == version.split(":")[-1]:
                target = v
                if "production" not in v.tags:
                    v.tags.append("production")
            else:
                v.tags = [t for t in v.tags if t != "production"]

        return target

    def update_metrics(
        self,
        project_id:  str,
        name:        str,
        version:     str,
        avg_score:   float,
        pass_rate:   float,
        total_traces: int,
    ) -> None:
        """Update quality metrics for a version (called by background worker)."""
        v = self.get(project_id, name, version)
        if v:
            v.avg_score    = avg_score
            v.pass_rate    = pass_rate
            v.total_traces = total_traces

    def _get_versions(
        self, project_id: str, name: str
    ) -> list[PromptVersion]:
        return (
            self._versions
            .get(project_id, {})
            .get(name, [])
        )


# Global registry — replace with DB-backed version in production
_registry = PromptRegistry()


def get_registry() -> PromptRegistry:
    return _registry