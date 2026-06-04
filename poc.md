# PoC.md — AI Presentation Generation Platform (Reduced Scope)
## Proof of Concept Specification v2.0

**Version:** 2.0  
**Scope:** Prompt-to-PPTX, no document ingestion, no vector store, no task queue  
**Timeline:** 2–3 weeks for one focused engineer  
**Goal:** User describes what they need → system thinks → system builds a cited, 
templated PPTX with no manual slide work from the user.

---

## 1. System Overview

The system is a conversational pipeline. The user interacts through a chat-style 
web UI. The backend is a stateful pipeline that moves through fixed stages. 
The user only makes two decisions: what they want (prompt) and which template 
to use. Everything else is handled by the system.

### Flow Summary
User enters prompt
↓
[A1] Intent Analysis
↓
System presents template options → User selects
↓
[A2] Knowledge Assessment
├── Sufficient knowledge → continue
└── Insufficient → ask clarifying questions → optionally request text → continue
↓
[A3] Storyboard Generation       (internal — user never sees this)
↓
[A4] Storyboard Verification     (internal — self-check loop, max 2 retries)
├── Pass → continue
└── Fail → regenerate storyboard → re-verify
↓
[A5] PPTX Generation
└── Images → placeholder text "Image showing: ___"
↓
System informs user → Download link
---

## 2. Scope

### Included

| Feature | Notes |
|---|---|
| Conversational web UI | Chat-style, not a form |
| Intent analysis | Determines type, audience, depth from prompt |
| Template selection | 3 pre-built templates; system presents, user picks |
| Knowledge assessment | LLM self-evaluates whether it knows enough |
| Clarifying question flow | Targeted questions if knowledge is insufficient |
| Optional context paste | User can paste text to fill knowledge gaps |
| Storyboard generation | Internal only — never shown to user |
| Storyboard self-verification | System checks its own storyboard before proceeding |
| PPTX generation | Populated from storyboard against selected template |
| Image placeholders | Text boxes: "Image showing: [description]" |
| Download link | Direct PPTX file download |
| 3 corporate templates | Corporate, Sales, Project Update |

### Excluded

| Feature | Phase |
|---|---|
| Document / PDF upload | Phase 2 |
| Internet research | Phase 3 |
| Vector store / knowledge repository | Phase 2 |
| Chart generation | Phase 3 |
| Task queue (Celery / Redis) | Phase 2 |
| Authentication / RBAC | Phase 4 |
| Storyboard shown to user | Post-PoC decision |
| User editing of storyboard | Post-PoC decision |

---

## 3. Technology Stack

### Backend

| Component | Technology | Rationale |
|---|---|---|
| API framework | FastAPI (Python 3.11+) | Async-native, SSE support built-in |
| Session state | In-memory dict + PostgreSQL | Simple; no Redis needed at this scale |
| Database | PostgreSQL 15 | Job state, conversation history, generated storyboards |
| LLM inference | Ollama (local, host machine) | On-premise, no data leakage |
| Primary LLM | deepseek-r1:8b | Strong reasoning, fits A4000 with headroom |
| PPTX generation | python-pptx | Programmatic slide population |
| Containerisation | Docker + Docker Compose | Single-command environment |

### Frontend

| Component | Technology | Rationale |
|---|---|---|
| UI style | Chat interface (vanilla JS + HTML + CSS) | Natural for a back-and-forth flow |
| Realtime updates | Server-Sent Events (SSE) | Pipeline status and typing indicators |
| No build tooling | Plain files | Zero setup friction for a PoC |

### Infrastructure
docker-compose.yml
├── api        (FastAPI — handles pipeline + serves frontend)
└── postgres   (job state + conversation history)
Ollama runs on host machine (GPU access)
API connects via host.docker.internal:11434
---

## 4. Conversation State Machine

Every user session is a job. A job moves through these stages in order. 
The stage determines what the backend does with the next user message.

```python
class JobStage(str, Enum):
    INTENT_ANALYSIS        = "intent_analysis"
    TEMPLATE_SELECTION     = "template_selection"
    KNOWLEDGE_ASSESSMENT   = "knowledge_assessment"
    CLARIFYING_QUESTIONS   = "clarifying_questions"
    CONTEXT_REQUEST        = "context_request"
    STORYBOARD_GENERATION  = "storyboard_generation"
    STORYBOARD_VERIFICATION = "storyboard_verification"
    PPTX_GENERATION        = "pptx_generation"
    COMPLETE               = "complete"
    FAILED                 = "failed"
```

Transitions are linear with two possible loops:
- `CLARIFYING_QUESTIONS` → `CONTEXT_REQUEST` → `STORYBOARD_GENERATION`
- `STORYBOARD_VERIFICATION` → `STORYBOARD_GENERATION` (on fail, max 2 retries)

---

## 5. Data Schemas

All schemas are Pydantic models in `api/models/schemas.py`.

```python
# api/models/schemas.py
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
    image_description: str | None  # e.g. "Bar chart showing revenue growth 2020–2024"


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
```

---

## 6. Agent Specifications

### Agent 1 — Intent Analysis

**Trigger:** User submits initial prompt  
**Purpose:** Determine presentation type, audience, depth, and which template to suggest  
**Output:** `IntentOutput`

```python
# api/agents/intent_agent.py
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from models.schemas import IntentOutput
import json

PROMPT = """
You are an expert presentation consultant.

A user has submitted the following request:
"{prompt}"

Analyse this request and return a JSON object with these exact fields:
- presentation_type: one of "executive_report", "project_update", "sales", 
  "training", "general"
- audience: who will receive this presentation (infer carefully from the prompt)
- objective: one sentence — what this presentation must achieve
- estimated_slides: integer between 8 and 20
- depth: one of "summary", "standard", "detailed"
- suggested_template: one of "corporate", "sales", "project_update"
  - Use "corporate" for executive reports, board updates, strategy
  - Use "sales" for client proposals, pitches, product decks
  - Use "project_update" for PMO, status reports, milestone tracking

Return only valid JSON. No explanation.
"""

class IntentAgent:
    def __init__(self):
        self.llm = ChatOllama(
            model="deepseek-r1:8b",
            base_url="http://host.docker.internal:11434",
            format="json",
            temperature=0.1
        )

    def run(self, prompt: str) -> IntentOutput:
        chain = ChatPromptTemplate.from_template(PROMPT) | self.llm
        result = chain.invoke({"prompt": prompt})
        return IntentOutput(**json.loads(result.content))
```

**What the system says to the user after this agent:**
"Got it. You're looking for a [presentation_type] for [audience].
Here are the available templates — which would you like to use?
[1] Corporate       — Clean executive layout, dark header, formal tone
[2] Sales           — Bold visuals, accent colours, persuasive structure
[3] Project Update  — Status-focused, RAG indicators, milestone layout
Type 1, 2, or 3."
---

### Agent 2 — Knowledge Assessment

**Trigger:** User selects a template  
**Purpose:** Determine whether the LLM has sufficient knowledge to build the 
storyboard, or whether it needs to ask the user for more information  
**Output:** `KnowledgeAssessmentOutput`

```python
# api/agents/knowledge_agent.py
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from models.schemas import IntentOutput, KnowledgeAssessmentOutput
import json

PROMPT = """
You are preparing to build a presentation with the following parameters:

Objective: {objective}
Audience: {audience}
Type: {presentation_type}
Depth required: {depth}

Before building, honestly assess your own knowledge:

1. Do you have sufficient, accurate, and up-to-date knowledge to populate 
   {estimated_slides} slides on this topic for this audience at this depth?
2. What aspects do you know well?
3. What aspects are you uncertain or uninformed about?
4. If knowledge is insufficient, what are the 1–3 most important clarifying 
   questions you would ask the user?
5. After asking questions, would you still need the user to paste in 
   reference text?

Be honest. It is better to ask than to generate inaccurate content.

Return a JSON object with these fields:
- is_sufficient: boolean
- confidence: float 0.0–1.0
- known_aspects: list of strings
- unknown_aspects: list of strings (empty if sufficient)
- clarifying_questions: list of strings, max 3 (empty if sufficient)
- needs_user_context: boolean (true only if questions alone won't be enough)

Return only valid JSON. No explanation.
"""

class KnowledgeAssessmentAgent:
    def __init__(self):
        self.llm = ChatOllama(
            model="deepseek-r1:8b",
            base_url="http://host.docker.internal:11434",
            format="json",
            temperature=0.1
        )

    def run(self, intent: IntentOutput) -> KnowledgeAssessmentOutput:
        chain = ChatPromptTemplate.from_template(PROMPT) | self.llm
        result = chain.invoke(intent.model_dump())
        return KnowledgeAssessmentOutput(**json.loads(result.content))
```

**Branching behaviour after this agent:**

```python
if assessment.is_sufficient:
    # Proceed silently to storyboard generation
    # Tell user: "Great, building your presentation now..."
    advance_to_storyboard(job)

elif not assessment.is_sufficient:
    # Ask the questions
    ask_clarifying_questions(job, assessment.clarifying_questions)
    advance_stage(job, JobStage.CLARIFYING_QUESTIONS)
    # After user answers:
    if assessment.needs_user_context:
        request_context_text(job)
        advance_stage(job, JobStage.CONTEXT_REQUEST)
    else:
        advance_to_storyboard(job)
```

**What the system says when asking questions:**
"Before I start building, I have a few questions to make sure
the content is accurate:

[clarifying_question_1]
[clarifying_question_2]
[clarifying_question_3]

Please answer each one — as much detail as you can."
**What the system says when requesting context text:**
"Thanks — that helps. One more thing: this topic has some
specifics I want to get right for your audience.
If you have any reference material — internal data, a report,
a brief — paste it here and I'll use it to ground the content.
Otherwise type 'skip' to continue with what we have."

---

### Agent 3 — Storyboard Generation

**Trigger:** Knowledge is sufficient (either natively or after clarification)  
**Purpose:** Generate a complete internal storyboard — slide by slide  
**Output:** `StoryboardOutput`  
**Visibility:** Never shown to the user

```python
# api/agents/storyboard_agent.py
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from models.schemas import IntentOutput, StoryboardOutput, SlideStoryboard
import json

SYSTEM_PROMPT = """
You are a senior presentation strategist. You build complete, 
executive-quality presentation storyboards. 
Your storyboards are used to generate PowerPoint files — they must be 
complete, coherent, and audience-appropriate.
Every slide must serve a purpose. No filler. No repetition.
"""

STORYBOARD_PROMPT = """
Build a complete storyboard for the following presentation:

Objective: {objective}
Audience: {audience}
Type: {presentation_type}
Depth: {depth}
Slide count target: {estimated_slides}

User's original request:
{original_prompt}

Additional context provided by user:
{user_context}

Instructions:
- First slide: title slide
- Last slide: closing / next steps
- Every other slide: content, data, or summary slide
- Each slide must have:
    - slide_title: short, punchy
    - slide_type: "title" | "content" | "data" | "summary" | "closing"
    - key_message: one sentence — what must the audience take away
    - bullet_points: 3–5 concrete, specific bullets (not vague)
    - speaker_notes: full narrative paragraph the presenter would say
    - image_required: true if a visual would meaningfully support this slide
    - image_description: if image_required, describe exactly what the image 
      should show (e.g. "Bar chart comparing Q1–Q4 revenue 2023 vs 2024")

Return a JSON object with:
- presentation_title: string
- executive_summary: 2–3 sentence summary of the whole presentation
- slides: array of slide objects as described above
- total_slides: integer

Return only valid JSON. No explanation.
"""

class StoryboardAgent:
    def __init__(self):
        self.llm = ChatOllama(
            model="deepseek-r1:8b",
            base_url="http://host.docker.internal:11434",
            format="json",
            temperature=0.4
        )

    def run(
        self,
        intent: IntentOutput,
        original_prompt: str,
        clarification_answers: list[str],
        user_context: str | None
    ) -> StoryboardOutput:

        context_text = user_context or "None provided."
        if clarification_answers:
            context_text = (
                "User answers to clarifying questions:\n"
                + "\n".join(f"- {a}" for a in clarification_answers)
                + ("\n\nAdditional context:\n" + user_context if user_context else "")
            )

        chain = (
            ChatPromptTemplate.from_messages([
                ("system", SYSTEM_PROMPT),
                ("human", STORYBOARD_PROMPT)
            ])
            | self.llm
        )

        result = chain.invoke({
            **intent.model_dump(),
            "original_prompt": original_prompt,
            "user_context": context_text,
        })

        data = json.loads(result.content)
        slides = [SlideStoryboard(slide_index=i, **s)
                  for i, s in enumerate(data["slides"])]

        return StoryboardOutput(
            presentation_title=data["presentation_title"],
            executive_summary=data["executive_summary"],
            slides=slides,
            total_slides=len(slides)
        )
```

---

### Agent 4 — Storyboard Verification

**Trigger:** Storyboard generation completes  
**Purpose:** Self-check the storyboard against intent, audience fit, 
narrative flow, and content completeness before any slides are built  
**Output:** `VerificationOutput`  
**Visibility:** Never shown to the user  
**Retry limit:** 2 regeneration attempts before proceeding anyway

```python
# api/agents/verification_agent.py
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from models.schemas import IntentOutput, StoryboardOutput, VerificationOutput
import json

PROMPT = """
You are a senior quality reviewer for executive presentations.

Review the following storyboard against the stated intent and audience. 
Be strict. This will be sent directly to stakeholders.

INTENT:
- Objective: {objective}
- Audience: {audience}
- Presentation type: {presentation_type}
- Required depth: {depth}

STORYBOARD TO REVIEW:
{storyboard_json}

Check for ALL of the following:

1. AUDIENCE FIT — Is the language, depth, and tone appropriate for {audience}?
2. OBJECTIVE ALIGNMENT — Does every slide serve the stated objective?
3. NARRATIVE FLOW — Does the presentation tell a coherent story from start 
   to finish? Are there logical gaps or jumps?
4. CONTENT COMPLETENESS — Are bullet points specific and substantive? 
   No vague filler like "discuss key challenges"?
5. SLIDE BALANCE — Is content distributed appropriately? No single slide 
   overloaded? No slides that are too thin?
6. OPENING AND CLOSING — Does the title slide set up the presentation 
   correctly? Does the closing slide land with clear next steps or takeaways?

Return a JSON object with:
- passes: boolean (true only if ALL checks pass)
- score: float 0.0–1.0 (overall quality)
- issues: list of specific problems found (empty if passes)
- fixes_required: list of specific changes needed (empty if passes)

Be honest and specific. Return only valid JSON. No explanation.
"""

class VerificationAgent:
    def __init__(self):
        self.llm = ChatOllama(
            model="deepseek-r1:8b",
            base_url="http://host.docker.internal:11434",
            format="json",
            temperature=0.0   # Deterministic for QA
        )

    def run(
        self,
        intent: IntentOutput,
        storyboard: StoryboardOutput
    ) -> VerificationOutput:

        storyboard_json = json.dumps({
            "presentation_title": storyboard.presentation_title,
            "slides": [
                {
                    "index": s.slide_index,
                    "title": s.slide_title,
                    "key_message": s.key_message,
                    "bullets": s.bullet_points,
                    "type": s.slide_type
                }
                for s in storyboard.slides
            ]
        }, indent=2)

        chain = ChatPromptTemplate.from_template(PROMPT) | self.llm
        result = chain.invoke({
            **intent.model_dump(),
            "storyboard_json": storyboard_json
        })

        return VerificationOutput(**json.loads(result.content))
```

**Retry loop logic (in pipeline controller):**

```python
MAX_STORYBOARD_ATTEMPTS = 2

async def run_storyboard_loop(job: Job) -> StoryboardOutput:
    storyboard_agent = StoryboardAgent()
    verification_agent = VerificationAgent()

    while job.storyboard_attempts < MAX_STORYBOARD_ATTEMPTS:
        job.storyboard_attempts += 1

        storyboard = storyboard_agent.run(
            intent=job.intent,
            original_prompt=job.original_prompt,
            clarification_answers=job.clarification_answers,
            user_context=job.user_context_text
        )
        job.storyboard = storyboard

        verification = verification_agent.run(job.intent, storyboard)
        job.verification = verification

        if verification.passes:
            return storyboard

        # Failed — log issues, retry with issues appended to context
        job.user_context_text = (
            (job.user_context_text or "") +
            "\n\nPrevious storyboard was rejected. Issues to fix:\n" +
            "\n".join(f"- {issue}" for issue in verification.fixes_required)
        )

    # Max retries reached — proceed with best available storyboard
    return job.storyboard
```

---

### Agent 5 — PPTX Generation

**Trigger:** Storyboard passes verification (or max retries reached)  
**Purpose:** Populate the selected template with storyboard content  
**Rules:**
- Template controls all fonts, colours, margins, and positions
- Agent only populates text content into named placeholders
- Images are replaced with a styled text box: `"Image showing: [description]"`
- Speaker notes are always written to slide notes

```python
# api/agents/rendering_agent.py
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
import os
from models.schemas import StoryboardOutput, SlideStoryboard

TEMPLATE_DIR = "/app/templates"
OUTPUT_DIR = "/app/outputs"

TEMPLATE_MAP = {
    "corporate":      "corporate.pptx",
    "sales":          "sales.pptx",
    "project_update": "project_update.pptx",
}

# Shape names that must exist in every template
# Set these in PowerPoint's Selection Pane before using
SHAPE_TITLE    = "Title"
SHAPE_BODY     = "Body"
SHAPE_SUBTITLE = "Subtitle"    # Title slide only
SHAPE_NOTE     = "SourceNote"  # Small footer text, optional

SLIDE_LAYOUT_MAP = {
    "title":   0,
    "content": 1,
    "data":    1,
    "summary": 1,
    "closing": 2,
}

class RenderingAgent:
    def __init__(self):
        os.makedirs(OUTPUT_DIR, exist_ok=True)

    def _get_shape(self, slide, name: str):
        for shape in slide.shapes:
            if shape.name == name and shape.has_text_frame:
                return shape
        return None

    def _set_text(self, shape, text: str, clear: bool = True):
        if shape is None:
            return
        tf = shape.text_frame
        if clear:
            tf.clear()
        tf.paragraphs[0].text = text

    def _set_bullets(self, shape, bullets: list[str]):
        if shape is None:
            return
        tf = shape.text_frame
        tf.clear()
        for i, bullet in enumerate(bullets[:5]):
            p = tf.add_paragraph() if i > 0 else tf.paragraphs[0]
            p.text = bullet
            p.level = 0

    def _add_image_placeholder(self, slide, description: str):
        """Add a styled text box as an image placeholder."""
        left   = Inches(1.0)
        top    = Inches(4.5)
        width  = Inches(8.0)
        height = Inches(1.8)

        box = slide.shapes.add_textbox(left, top, width, height)
        tf = box.text_frame
        tf.word_wrap = True

        p = tf.paragraphs[0]
        p.text = f"Image showing: {description}"
        p.alignment = PP_ALIGN.CENTER

        run = p.runs[0]
        run.font.size = Pt(13)
        run.font.italic = True
        run.font.color.rgb = RGBColor(0x88, 0x88, 0x88)

        # Dashed border on the box
        from pptx.oxml.ns import qn
        from lxml import etree
        sp_pr = box.shape._element.spPr
        ln = etree.SubElement(sp_pr, qn('a:ln'))
        ln.set('w', '12700')
        dash = etree.SubElement(ln, qn('a:prstDash'))
        dash.set('val', 'dash')
        solid = etree.SubElement(ln, qn('a:solidFill'))
        clr = etree.SubElement(solid, qn('a:srgbClr'))
        clr.set('val', 'AAAAAA')

    def _write_speaker_notes(self, slide, notes_text: str):
        notes_slide = slide.notes_slide
        tf = notes_slide.notes_text_frame
        tf.text = notes_text

    def populate_title_slide(self, slide, data: SlideStoryboard, prs_title: str):
        self._set_text(self._get_shape(slide, SHAPE_TITLE), prs_title)
        self._set_text(self._get_shape(slide, SHAPE_SUBTITLE), data.key_message)
        self._write_speaker_notes(slide, data.speaker_notes)

    def populate_content_slide(self, slide, data: SlideStoryboard):
        self._set_text(self._get_shape(slide, SHAPE_TITLE), data.slide_title)
        self._set_bullets(self._get_shape(slide, SHAPE_BODY), data.bullet_points)
        if data.image_required and data.image_description:
            self._add_image_placeholder(slide, data.image_description)
        self._write_speaker_notes(slide, data.speaker_notes)

    def run(
        self,
        job_id: str,
        template_name: str,
        storyboard: StoryboardOutput
    ) -> str:
        template_file = TEMPLATE_MAP.get(template_name, "corporate.pptx")
        template_path = os.path.join(TEMPLATE_DIR, template_file)

        prs = Presentation(template_path)

        # Clear all slides from template, keep layouts
        xml_slides = prs.slides._sldIdLst
        for _ in range(len(prs.slides)):
            xml_slides.remove(xml_slides[0])

        for slide_data in storyboard.slides:
            layout_idx = SLIDE_LAYOUT_MAP.get(slide_data.slide_type, 1)
            layout = prs.slide_layouts[layout_idx]
            slide = prs.slides.add_slide(layout)

            if slide_data.slide_type == "title":
                self.populate_title_slide(
                    slide, slide_data, storyboard.presentation_title
                )
            else:
                self.populate_content_slide(slide, slide_data)

        output_path = os.path.join(OUTPUT_DIR, f"{job_id}.pptx")
        prs.save(output_path)
        return output_path
```

---

## 7. Pipeline Controller

The controller is the single place that advances the job through stages. 
It is called by the API router on every user message.

```python
# api/pipeline/controller.py
import asyncio
from models.schemas import Job, JobStage
from agents.intent_agent import IntentAgent
from agents.knowledge_agent import KnowledgeAssessmentAgent
from agents.storyboard_agent import StoryboardAgent
from agents.verification_agent import VerificationAgent
from agents.rendering_agent import RenderingAgent
from services.db import save_job
from services.sse import emit

MAX_STORYBOARD_ATTEMPTS = 2

async def advance(job: Job, user_message: str) -> str:
    """
    Called on every user message.
    Advances the job to the next stage and returns the assistant's reply.
    """

    # ── Stage: initial prompt received ────────────────────────
    if job.stage == JobStage.INTENT_ANALYSIS:
        intent = IntentAgent().run(user_message)
        job.intent = intent
        job.original_prompt = user_message
        job.stage = JobStage.TEMPLATE_SELECTION
        await save_job(job)

        template_hint = intent.suggested_template.replace("_", " ").title()
        return (
            f"Got it. You need a **{intent.presentation_type.replace('_',' ').title()}** "
            f"for **{intent.audience}**.\n\n"
            f"Please choose a template:\n\n"
            f"**[1] Corporate** — Clean executive layout, formal tone\n"
            f"**[2] Sales** — Bold accents, persuasive structure\n"
            f"**[3] Project Update** — Status-focused, milestone layout\n\n"
            f"*(Based on your request, I'd suggest **{template_hint}**.)*\n\n"
            f"Type 1, 2, or 3."
        )

    # ── Stage: user selects template ──────────────────────────
    if job.stage == JobStage.TEMPLATE_SELECTION:
        template_map = {"1": "corporate", "2": "sales", "3": "project_update"}
        selected = template_map.get(user_message.strip(), "corporate")
        job.selected_template = selected
        job.stage = JobStage.KNOWLEDGE_ASSESSMENT
        await save_job(job)

        # Run knowledge assessment immediately (no user input needed)
        assessment = KnowledgeAssessmentAgent().run(job.intent)
        job.knowledge_assessment = assessment

        if assessment.is_sufficient:
            job.stage = JobStage.STORYBOARD_GENERATION
            await save_job(job)
            # Fire-and-forget the storyboard pipeline
            asyncio.create_task(run_generation_pipeline(job))
            return (
                f"**{selected.replace('_',' ').title()}** template selected. "
                f"Building your presentation now — I'll let you know when it's ready."
            )
        else:
            job.stage = JobStage.CLARIFYING_QUESTIONS
            await save_job(job)
            questions = "\n".join(
                f"{i+1}. {q}"
                for i, q in enumerate(assessment.clarifying_questions)
            )
            return (
                f"Before I start, I have a few questions to make sure "
                f"the content is accurate:\n\n{questions}\n\n"
                f"Please answer each one."
            )

    # ── Stage: user answers clarifying questions ───────────────
    if job.stage == JobStage.CLARIFYING_QUESTIONS:
        job.clarification_answers.append(user_message)
        assessment = job.knowledge_assessment

        if assessment.needs_user_context:
            job.stage = JobStage.CONTEXT_REQUEST
            await save_job(job)
            return (
                "Thanks — that helps a lot.\n\n"
                "One more thing: if you have any reference material — "
                "internal data, a brief, a report — paste it here and "
                "I'll use it to ground the content accurately.\n\n"
                "Otherwise type **skip** to continue."
            )
        else:
            job.stage = JobStage.STORYBOARD_GENERATION
            await save_job(job)
            asyncio.create_task(run_generation_pipeline(job))
            return "Got it. Building your presentation now — I'll let you know when it's ready."

    # ── Stage: user pastes context or skips ───────────────────
    if job.stage == JobStage.CONTEXT_REQUEST:
        if user_message.strip().lower() != "skip":
            job.user_context_text = user_message
        job.stage = JobStage.STORYBOARD_GENERATION
        await save_job(job)
        asyncio.create_task(run_generation_pipeline(job))
        return "Perfect. Building your presentation now — I'll let you know when it's ready."

    return "Your presentation is being generated. Please wait."


async def run_generation_pipeline(job: Job):
    """
    Runs silently in the background.
    User is not involved in this stage.
    """
    try:
        storyboard_agent    = StoryboardAgent()
        verification_agent  = VerificationAgent()
        rendering_agent     = RenderingAgent()

        # ── Storyboard + verification loop ────────────────────
        job.stage = JobStage.STORYBOARD_GENERATION
        await save_job(job)

        while job.storyboard_attempts < MAX_STORYBOARD_ATTEMPTS:
            job.storyboard_attempts += 1

            storyboard = storyboard_agent.run(
                intent=job.intent,
                original_prompt=job.original_prompt,
                clarification_answers=job.clarification_answers,
                user_context=job.user_context_text
            )
            job.storyboard = storyboard

            job.stage = JobStage.STORYBOARD_VERIFICATION
            await save_job(job)

            verification = verification_agent.run(job.intent, storyboard)
            job.verification = verification

            if verification.passes:
                break

            # Inject issues back into context for the next attempt
            job.user_context_text = (
                (job.user_context_text or "") +
                "\n\nPrevious attempt had issues:\n" +
                "\n".join(f"- {fix}" for fix in verification.fixes_required)
            )

        # ── PPTX rendering ─────────────────────────────────────
        job.stage = JobStage.PPTX_GENERATION
        await save_job(job)

        pptx_path = rendering_agent.run(
            job_id=job.job_id,
            template_name=job.selected_template,
            storyboard=job.storyboard
        )
        job.pptx_path = pptx_path
        job.stage = JobStage.COMPLETE
        await save_job(job)

        # Notify user via SSE
        await emit(job.job_id, {
            "type": "complete",
            "message": (
                f"Your presentation is ready — "
                f"**{job.storyboard.total_slides} slides** generated.\n\n"
                f"[Download your PPTX](/api/v1/jobs/{job.job_id}/download)"
            )
        })

    except Exception as e:
        job.stage = JobStage.FAILED
        job.error = str(e)
        await save_job(job)
        await emit(job.job_id, {
            "type": "error",
            "message": f"Something went wrong: {str(e)}. Please try again."
        })
```

---

## 8. API Specification

### POST `/api/v1/jobs`
Start a new job (first user message).

**Request:**
```json
{ "message": "Create a sales deck for UAE banking clients targeting CFOs" }
```

**Response `201`:**
```json
{
  "job_id": "uuid",
  "reply": "Got it. You need a Sales presentation for CFO-level banking clients...",
  "stage": "template_selection"
}
```

---

### POST `/api/v1/jobs/{job_id}/message`
Send the next user message in the conversation.

**Request:**
```json
{ "message": "2" }
```

**Response `200`:**
```json
{
  "job_id": "uuid",
  "reply": "Sales template selected. Building your presentation now...",
  "stage": "storyboard_generation"
}
```

---

### GET `/api/v1/jobs/{job_id}/stream`
SSE stream for background pipeline updates.

**Events:**
event: status
data: {"type": "progress", "message": "Analysing your topic..."}
event: status
data: {"type": "progress", "message": "Verifying content quality..."}
event: status
data: {"type": "complete", "message": "Your presentation is ready — 12 slides generated.",
"download_url": "/api/v1/jobs/uuid/download"}
event: status
data: {"type": "error", "message": "Something went wrong. Please try again."}
---

### GET `/api/v1/jobs/{job_id}/download`
Download the generated PPTX.

**Response `200`:**
Content-Type: application/vnd.openxmlformats-officedocument.presentationml.presentation
Content-Disposition: attachment; filename="presentation.pptx"
---

## 9. Database Schema

```sql
CREATE TABLE jobs (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stage                 VARCHAR(50) NOT NULL DEFAULT 'intent_analysis',
    original_prompt       TEXT,
    selected_template     VARCHAR(50),
    clarification_answers JSONB DEFAULT '[]',
    user_context_text     TEXT,
    intent_json           JSONB,
    knowledge_json        JSONB,
    storyboard_json       JSONB,
    verification_json     JSONB,
    storyboard_attempts   INTEGER DEFAULT 0,
    pptx_path             TEXT,
    error                 TEXT,
    messages              JSONB DEFAULT '[]',
    created_at            TIMESTAMPTZ DEFAULT NOW(),
    updated_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_jobs_stage ON jobs(stage);
```

---

## 10. Project Structure
poc/
├── docker-compose.yml
├── .env.example
├── README.md
│
├── api/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   ├── routers/
│   │   └── jobs.py
│   ├── models/
│   │   └── schemas.py
│   ├── agents/
│   │   ├── intent_agent.py
│   │   ├── knowledge_agent.py
│   │   ├── storyboard_agent.py
│   │   ├── verification_agent.py
│   │   └── rendering_agent.py
│   ├── pipeline/
│   │   └── controller.py
│   └── services/
│       ├── db.py
│       └── sse.py
│
├── templates/
│   ├── corporate.pptx
│   ├── sales.pptx
│   └── project_update.pptx
│
├── outputs/
│
└── frontend/
├── index.html
└── static/
├── app.js
└── style.css

---

## 11. Docker Compose

```yaml
version: "3.9"

services:
  api:
    build: ./api
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://poc:poc@postgres:5432/poc
      - OLLAMA_BASE_URL=http://host.docker.internal:11434
      - OUTPUT_DIR=/app/outputs
      - TEMPLATE_DIR=/app/templates
    volumes:
      - ./outputs:/app/outputs
      - ./templates:/app/templates
    depends_on:
      - postgres
    extra_hosts:
      - "host.docker.internal:host-gateway"

  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: poc
      POSTGRES_PASSWORD: poc
      POSTGRES_DB: poc
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

---

## 12. requirements.txt
fastapi==0.111.0
uvicorn[standard]==0.29.0
psycopg2-binary==2.9.9
sqlalchemy==2.0.30
pydantic==2.7.1
langchain==0.2.1
langchain-ollama==0.1.0
langchain-core==0.2.1
python-pptx==0.6.23
lxml==5.2.2
sse-starlette==2.1.0
python-dotenv==1.0.1
httpx==0.27.0
---

## 13. Ollama Setup

```bash
# On the host machine before docker compose up
ollama pull deepseek-r1:8b
ollama list
curl http://localhost:11434/api/tags   # confirm running
```

---

## 14. Build & Run

```bash
git clone <repo> poc && cd poc
cp .env.example .env

# Add your three template files
cp /path/to/corporate.pptx     templates/corporate.pptx
cp /path/to/sales.pptx         templates/sales.pptx
cp /path/to/project_update.pptx templates/project_update.pptx

docker compose up --build

# First run — initialise DB
docker compose exec api python -c "from services.db import init_db; init_db()"

open http://localhost:8000
```

---

## 15. Template Requirements

Each `.pptx` template must have the following shape names set via 
PowerPoint's **Selection Pane** (Home → Arrange → Selection Pane):

| Shape name | Required on | Purpose |
|---|---|---|
| `Title` | All slide layouts | Slide title text |
| `Body` | Content layouts (1, 2) | Bullet points |
| `Subtitle` | Title layout (0) | Subtitle / key message |
| `SourceNote` | Content layouts (optional) | Footer citation text |

Layout index assignments (must match template):

| Index | Layout name | Used for |
|---|---|---|
| 0 | Title Slide | First slide |
| 1 | Content | All body slides |
| 2 | Section/Closing | Last slide |

---

## 16. Known PoC Limitations

| Limitation | Acceptable for PoC? | Addressed in |
|---|---|---|
| No document upload | Yes — prompt + context paste covers it | Phase 2 |
| No internet research | Yes — LLM knowledge + user context | Phase 3 |
| No chart generation | Yes — image placeholders communicate intent | Phase 3 |
| LLM output non-deterministic | Yes — verification loop compensates | Ongoing |
| Storyboard not user-editable | Yes — internal quality loop instead | Post-PoC |
| Single user, no auth | Yes | Phase 4 |
| Template shape names must be manually set | Yes — one-time setup | Phase 4 |