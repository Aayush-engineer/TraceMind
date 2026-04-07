from sqlalchemy import (Column, String, Float, Integer, Boolean,
                         Text, JSON, ForeignKey, DateTime, Index)
from sqlalchemy.orm import declarative_base
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
    timestamp   = Column(Float,  nullable=False)   # Unix timestamp

    __table_args__ = (
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