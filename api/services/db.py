# api/services/db.py

import os
import json
from sqlalchemy import create_engine, Column, String, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Session
from models.schemas import Job, JobStage

from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


engine = create_engine(DATABASE_URL)


class Base(DeclarativeBase):
    pass


class JobRecord(Base):
    __tablename__ = "jobs"

    id                    = Column(String, primary_key=True)
    stage                 = Column(String, nullable=False, default="intent_analysis")
    original_prompt       = Column(Text)
    selected_template     = Column(String)
    clarification_answers = Column(JSONB, default=list)
    user_context_text     = Column(Text)
    intent_json           = Column(JSONB)
    knowledge_json        = Column(JSONB)
    storyboard_json       = Column(JSONB)
    verification_json     = Column(JSONB)
    storyboard_attempts   = Column(Integer, default=0)
    pptx_path             = Column(Text)
    error                 = Column(Text)
    messages              = Column(JSONB, default=list)


def init_db():
    Base.metadata.create_all(engine)


def save_job(job: Job):
    with Session(engine) as session:
        record = session.get(JobRecord, job.job_id)

        if record is None:
            record = JobRecord(id=job.job_id)
            session.add(record)

        record.stage                 = job.stage.value
        record.original_prompt       = job.original_prompt
        record.selected_template     = job.selected_template
        record.clarification_answers = job.clarification_answers
        record.user_context_text     = job.user_context_text
        record.intent_json           = job.intent.model_dump() if job.intent else None
        record.knowledge_json        = job.knowledge_assessment.model_dump() if job.knowledge_assessment else None
        record.storyboard_json       = job.storyboard.model_dump() if job.storyboard else None
        record.verification_json     = job.verification.model_dump() if job.verification else None
        record.storyboard_attempts   = job.storyboard_attempts
        record.pptx_path             = job.pptx_path
        record.error                 = job.error
        record.messages              = job.messages

        session.commit()


def load_job(job_id: str) -> Job | None:
    with Session(engine) as session:
        record = session.get(JobRecord, job_id)

        if record is None:
            return None

        from models.schemas import (
            IntentOutput, KnowledgeAssessmentOutput,
            StoryboardOutput, VerificationOutput
        )

        return Job(
            job_id                = record.id,
            stage                 = JobStage(record.stage),
            original_prompt       = record.original_prompt or "",
            selected_template     = record.selected_template,
            clarification_answers = record.clarification_answers or [],
            user_context_text     = record.user_context_text,
            intent                = IntentOutput(**record.intent_json) if record.intent_json else None,
            knowledge_assessment  = KnowledgeAssessmentOutput(**record.knowledge_json) if record.knowledge_json else None,
            storyboard            = StoryboardOutput(**record.storyboard_json) if record.storyboard_json else None,
            verification          = VerificationOutput(**record.verification_json) if record.verification_json else None,
            storyboard_attempts   = record.storyboard_attempts or 0,
            pptx_path             = record.pptx_path,
            error                 = record.error,
            messages              = record.messages or [],
        )