from sqlalchemy import (Column, String, Float, Integer, Boolean,
                         Text, JSON, ForeignKey, DateTime, Index, UniqueConstraint)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
from datetime import datetime
import uuid
import time
Base = declarative_base()

def gen_id():
    return str(uuid.uuid4())[:12]

class Project(Base):
    __tablename__ = "projects"
    id          = Column(String, primary_key=True, default=gen_id)
    name        = Column(String, nullable=False, unique=True)
    description = Column(Text, default="")
    api_key     = Column(String, nullable=False, unique=True)
    webhook_url = Column(String, nullable=True)    # ← add this line
    created_at  = Column(DateTime, default=datetime.utcnow)
    ab_test_runs = relationship("ABTestRun",     back_populates="project", cascade="all, delete-orphan")
    cost_records = relationship("CostRecord",    back_populates="project", cascade="all, delete-orphan")

class Span(Base):
    __tablename__ = "spans"
    id          = Column(String, primary_key=True, default=gen_id)
    span_id     = Column(String, nullable=False)
    trace_id    = Column(String, nullable=False, index=True)
    project_id  = Column(String, ForeignKey("projects.id"), nullable=False)
    name        = Column(String, nullable=False)   # e.g. "rag_retrieval"
    input       = Column(Text, default="")
    output      = Column(Text, default="")
    error       = Column(Text, default="")
    duration_ms = Column(Float, default=0.0)
    judge_score = Column(Float, nullable=True)     # auto-scored
    status      = Column(String, default="success")
    tags        = Column(JSON,   default=list)
    span_metadata = Column("metadata", JSON, default=dict)
    cost_usd    = Column(Float,  default=0.0)
    tokens_in   = Column(Integer, default=0)
    tokens_out  = Column(Integer, default=0)
    timestamp   = Column(Float,  nullable=False)   
    tool_calls_json = Column(JSON, default=list)

    __table_args__ = (
        UniqueConstraint("span_id", name="uq_spans_span_id"),
        Index("idx_spans_project_ts", "project_id", "timestamp"),
        Index("idx_spans_name",       "project_id", "name"),
    )

class Dataset(Base):
    __tablename__ = "datasets"
    id          = Column(String, primary_key=True, default=gen_id)
    project_id  = Column(String, ForeignKey("projects.id"), nullable=False)
    name        = Column(String, nullable=False)
    description = Column(Text, default="")
    version     = Column(String, default="1.0")
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class DatasetExample(Base):
    __tablename__ = "dataset_examples"
    id          = Column(String, primary_key=True, default=gen_id)
    dataset_id  = Column(String, ForeignKey("datasets.id"), nullable=False)
    input       = Column(Text, nullable=False)
    expected    = Column(Text, default="")
    criteria    = Column(JSON, default=list)     # ["accurate", "professional"]
    category    = Column(String, default="general")
    difficulty  = Column(String, default="medium")
    tags        = Column(JSON, default=list)
    verified    = Column(Boolean, default=False)
    source      = Column(String, default="human") # human/synthetic/production
    notes       = Column(Text, default="")

class EvalRun(Base):
    __tablename__ = "eval_runs"
    id           = Column(String, primary_key=True, default=gen_id)
    project_id   = Column(String, ForeignKey("projects.id"), nullable=False)
    dataset_id   = Column(String, ForeignKey("datasets.id"), nullable=False)
    name         = Column(String, default="")     # "pre-deploy check"
    status       = Column(String, default="pending")  # pending/running/completed/failed
    pass_rate    = Column(Float,  nullable=True)
    avg_score    = Column(Float,  nullable=True)
    total_cases  = Column(Integer, default=0)
    passed_cases = Column(Integer, default=0)
    failed_cases = Column(Integer, default=0)
    config       = Column(JSON, default=dict)     # model, judge_criteria, etc.
    git_commit   = Column(String, default="")     # link eval to code version
    started_at   = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at   = Column(DateTime, default=datetime.utcnow)

class EvalResult(Base):
    __tablename__ = "eval_results"
    id              = Column(String, primary_key=True, default=gen_id)
    run_id          = Column(String, ForeignKey("eval_runs.id"), nullable=False)
    example_id      = Column(String, ForeignKey("dataset_examples.id"), nullable=False)
    input           = Column(Text, default="")
    expected        = Column(Text, default="")
    actual_output   = Column(Text, default="")
    judge_score     = Column(Float, nullable=True)
    passed          = Column(Boolean, default=False)
    dimension_scores = Column(JSON, default=dict)
    judge_reasoning = Column(Text, default="")
    latency_ms      = Column(Float, default=0.0)
    cost_usd        = Column(Float, default=0.0)
    error           = Column(Text, default="")
    confidence       = Column(String,  default="medium")
    is_ambiguous     = Column(Boolean, default=False)
    ci_lower         = Column(Float,   default=0.0)
    ci_upper         = Column(Float,   default=0.0)
    reference_match  = Column(Float,   nullable=True)
    factual_contradiction = Column(Boolean, default=False)
    improvement      = Column(Text,    default="")
    task_type        = Column(String,  default="general")
    task_metrics_json = Column(JSON,   default=dict)

class Alert(Base):
    __tablename__ = "alerts"
    id           = Column(String, primary_key=True, default=gen_id)
    project_id   = Column(String, ForeignKey("projects.id"), nullable=False)
    type         = Column(String, nullable=False)  # quality_regression/error_spike/latency
    severity     = Column(String, default="medium")  # low/medium/high/critical
    message      = Column(Text, nullable=False)
    metric_value = Column(Float, nullable=True)
    threshold    = Column(Float, nullable=True)
    resolved     = Column(Boolean, default=False)
    webhook_sent = Column(Boolean, default=False)
    created_at   = Column(DateTime, default=datetime.utcnow)
    resolved_at  = Column(DateTime, nullable=True)
    webhook_url  = Column(String,   nullable=True)   # per-project alert destination


class AgentEpisode(Base):
    __tablename__ = "agent_episodes"

    id          = Column(String, primary_key=True, default=gen_id)
    project_id  = Column(String, ForeignKey("projects.id"), nullable=False)
    query       = Column(Text,   nullable=False)      # what the user asked
    steps_json  = Column(Text,   default="[]")        # tool calls taken
    answer      = Column(Text,   default="")          # final answer given
    was_helpful = Column(Boolean, nullable=True)      # user feedback (future)
    tokens_used = Column(Integer, default=0)
    iterations  = Column(Integer, default=0)
    timestamp   = Column(Float,   nullable=False, default=lambda: __import__("time").time())
    created_at  = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_episodes_project_ts", "project_id", "timestamp"),
    )

class AgentRun(Base):
    __tablename__ = "agent_runs"

    id          = Column(String,  primary_key=True)
    project_id  = Column(String,  nullable=False, index=True)
    query       = Column(Text,    nullable=False)
    status      = Column(String,  default="running")
    answer      = Column(Text,    default="")
    steps_json  = Column(Text,    default="[]")
    iterations  = Column(Integer, default=0)
    tokens_used = Column(Integer, default=0)
    error       = Column(Text,    default="")
    started_at  = Column(Float,   default=time.time)
    finished_at = Column(Float,   nullable=True)


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id           = Column(String,  primary_key=True, default=lambda: str(uuid.uuid4())[:13])
    version_id   = Column(String,  nullable=False, unique=True)   # "support_prompt:v3"
    name         = Column(String,  nullable=False)
    version_num  = Column(Integer, nullable=False)
    project_id   = Column(String,  ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    content      = Column(Text,    nullable=False)
    content_hash = Column(String,  nullable=False)
    tags         = Column(JSON,    default=list)
    author       = Column(String,  default="api")
    description  = Column(String,  default="")
    parent_version = Column(String, nullable=True)
    avg_score    = Column(Float,   nullable=True)
    pass_rate    = Column(Float,   nullable=True)
    total_traces = Column(Integer, default=0)
    created_at   = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("project_id", "name", "version_num", name="uq_prompt_version"),
    )

class ABTestRun(Base):
    __tablename__ = "ab_test_runs"
    id             = Column(String(12), primary_key=True, default=gen_id)
    project_id     = Column(String(12), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name           = Column(String(255), nullable=False)
    status         = Column(String(32),  default="running")
    dataset_name   = Column(String(255), nullable=False)
    prompt_a       = Column(Text, nullable=False)
    prompt_b       = Column(Text, nullable=False)
    criteria_json  = Column(JSON, default=list)
    result_json    = Column(JSON, nullable=True)
    pass_rate_a    = Column(Float, nullable=True)
    pass_rate_b    = Column(Float, nullable=True)
    avg_score_a    = Column(Float, nullable=True)
    avg_score_b    = Column(Float, nullable=True)
    winner         = Column(String(8), nullable=True)
    p_value        = Column(Float, nullable=True)
    effect_size    = Column(Float, nullable=True)
    created_at     = Column(Float, default=time.time)
    completed_at   = Column(Float, nullable=True)
    project        = relationship("Project", back_populates="ab_test_runs")


class CostRecord(Base):
    __tablename__ = "cost_records"
    id          = Column(String(12), primary_key=True, default=gen_id)
    project_id  = Column(String(12), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    span_id     = Column(String(12), nullable=True)
    provider    = Column(String(32), nullable=False)
    model       = Column(String(64), nullable=False)
    operation   = Column(String(64), nullable=False)
    tokens_in   = Column(Integer, default=0)
    tokens_out  = Column(Integer, default=0)
    cost_usd    = Column(Float, default=0.0)
    timestamp   = Column(Float, default=time.time, nullable=False)
    project     = relationship("Project", back_populates="cost_records")


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    id              = Column(String(12), primary_key=True, default=gen_id)
    alert_id        = Column(String(12), ForeignKey("alerts.id"), nullable=True)
    project_id      = Column(String(12), nullable=False)
    webhook_url     = Column(String(2000), nullable=False)
    payload_json    = Column(JSON, nullable=False)
    status          = Column(String(16), default="pending")
    attempts        = Column(Integer, default=0)
    last_attempt_at = Column(Float, nullable=True)
    next_retry_at   = Column(Float, default=time.time)
    error_detail    = Column(Text, nullable=True)
    created_at      = Column(Float, default=time.time)