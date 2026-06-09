from pydantic import BaseModel
from typing import Optional
from enum import Enum
import uuid
from datetime import datetime


class JobStage(str, Enum):
    INTENT_ANALYSIS         = "intent_analysis"
    TEMPLATE_SELECTION      = "template_selection"
    KNOWLEDGE_ASSESSMENT    = "knowledge_assessment"
    CLARIFYING_QUESTIONS    = "clarifying_questions"
    CONTEXT_REQUEST         = "context_request"
    STORYBOARD_GENERATION   = "storyboard_generation"
    STORYBOARD_VERIFICATION = "storyboard_verification"
    CHART_DATA_COLLECTION   = "chart_data_collection"
    PPTX_GENERATION         = "pptx_generation"
    COMPLETE                = "complete"
    FAILED                  = "failed"


class PresentationType(str, Enum):
    EXECUTIVE_REPORT = "executive_report"
    PROJECT_UPDATE   = "project_update"
    SALES            = "sales"
    TRAINING         = "training"
    GENERAL          = "general"


# ── Agent outputs ──────────────────────────────────────────────

class IntentOutput(BaseModel):
    presentation_type: PresentationType
    audience: str               # e.g. "C-suite leadership"
    objective: str              # One sentence
    estimated_slides: int       # 8–20
    depth: str                  # "summary" | "standard" | "detailed"
    suggested_template: str     # "corporate" | "sales" | "project_update"
    contains_user_data: bool = False


class KnowledgeAssessmentOutput(BaseModel):
    is_sufficient: bool
    confidence: float           # 0.0–1.0
    known_aspects: list[str]    # What the LLM knows well
    unknown_aspects: list[str]  # What it doesn't know
    clarifying_questions: list[str]  # Max 3, only if not sufficient
    needs_user_context: bool    # Whether to request pasted text after questions


class SlideStoryboard(BaseModel):
    slide_index: int
    slide_title: str
    slide_type: str             # "title"|"content"|"data"|"summary"|"closing"
    key_message: str            # One sentence: what this slide must convey
    bullet_points: list[str]    # 3–5 bullets
    speaker_notes: str          # Full narrative paragraph
    image_required: bool
    image_description: str | None = None  # e.g. "Bar chart showing revenue growth 2020–2024"


class StoryboardOutput(BaseModel):
    presentation_title: str
    executive_summary: str
    slides: list[SlideStoryboard]
    total_slides: int


class VerificationOutput(BaseModel):
    passes: bool
    score: float                # 0.0–1.0
    issues: list[str]           # Specific problems found
    fixes_required: list[str]   # What must change if not passing


# ── Job state ──────────────────────────────────────────────────

class Job(BaseModel):
    job_id: str = str(uuid.uuid4())
    stage: JobStage = JobStage.INTENT_ANALYSIS
    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()

    # User inputs
    original_prompt: str = ""
    selected_template: str | None = None
    clarification_answers: list[str] = []
    user_context_text: str | None = None

    # Agent outputs
    intent: IntentOutput | None = None
    knowledge_assessment: KnowledgeAssessmentOutput | None = None
    storyboard: StoryboardOutput | None = None
    verification: VerificationOutput | None = None
    storyboard_attempts: int = 0

    # Result
    pptx_path: str | None = None
    error: str | None = None

    # Conversation history for the UI
    messages: list[dict] = []   # {"role": "user"|"assistant", "text": str}

    #Chart Slides
    chart_slides: list[int] = []          # slide indices that need charts
    current_chart_index: int = 0          # which chart we are currently collecting for
    chart_data: dict[int, dict] = {}      # slide_index → {raw_data, chart_type, png_path}


