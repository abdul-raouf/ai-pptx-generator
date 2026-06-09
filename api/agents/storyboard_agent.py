from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from models.schemas import IntentOutput, StoryboardOutput, SlideStoryboard
import json

SYSTEM = """
You are a senior presentation strategist. You build complete, executive-quality 
presentation storyboards. Every slide must serve a clear purpose. No filler. No repetition.
"""

PROMPT = """
Build a complete storyboard for the following presentation:

Objective: {objective}
Audience: {audience}
Type: {presentation_type}


Slide count rules based on depth — follow these strictly:
- "summary"  → exactly 6 to 8 slides
- "standard" → exactly 9 to 12 slides  
- "detailed" → exactly 13 to 16 slides

Current depth: {depth}
Target slide count: {slide_count_range}

Do not exceed the upper bound. Do not pad with redundant slides.
Every slide must earn its place.

User's original request:
{original_prompt}

Additional context:
{user_context}

Rules:
- First slide must be a title slide.
- Last slide must be a closing or next steps slide
- Every slide needs: slide_title, slide_type, key_message, bullet_points (3-5), speaker_notes, image_required, image_description
- slide_type is one of: "title", "content", "data", "summary", "closing"
- image_description is required only when image_required is true — describe exactly what the image should show
- bullet_points must be specific and concrete, not vague
- image_required: true ONLY for data or chart slides where a visual is essential or when an image explains the context better.

Return a JSON object with:
- presentation_title: string (brief title of no more than 5-6 words.)
- executive_summary: string (2-3 sentences)
- slides: array of slide objects
- total_slides: integer

Return only valid JSON. No explanation.
"""

DEPTH_RANGE = {
    "summary":  "6–8",
    "standard": "9–12",
    "detailed": "13–16",
}

class StoryboardAgent:
    def __init__(self):
        self.llm = ChatOllama(
            model="qwen3.6:27b",
            base_url="http://localhost:11434",
            format="json",
            temperature=0.3
        )

    def run(self, intent: IntentOutput, original_prompt: str, clarification_answers: list[str], user_context: str | None) -> StoryboardOutput:
        context = user_context or "None provided."
        if clarification_answers:
            context = (
                "User answers to clarifying questions:\n"
                + "\n".join(f"- {a}" for a in clarification_answers)
                + ("\n\nAdditional context:\n" + user_context if user_context else "")
            )

        

        chain = ChatPromptTemplate.from_messages([
            ("system", SYSTEM),
            ("human", PROMPT)
        ]) | self.llm

        result = chain.invoke({
            **intent.model_dump(),
            "original_prompt": original_prompt,
            "user_context": context,
            "slide_count_range": DEPTH_RANGE.get(intent.depth, "9–12"),
        })

        data = json.loads(result.content)
        slides = [SlideStoryboard(slide_index=i, **s) for i, s in enumerate(data["slides"])]

        return StoryboardOutput(
            presentation_title=data["presentation_title"],
            executive_summary=data["executive_summary"],
            slides=slides,
            total_slides=len(slides)
        )