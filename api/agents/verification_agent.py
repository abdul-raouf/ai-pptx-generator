from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from models.schemas import IntentOutput, StoryboardOutput, VerificationOutput
import json

PROMPT = """
You are a senior quality reviewer for executive presentations.

Review the following storyboard against the stated intent and audience.

INTENT:
- Objective: {objective}
- Audience: {audience}
- Type: {presentation_type}
- Depth: {depth}

STORYBOARD:
{storyboard_json}

Check all of the following:
1. AUDIENCE FIT — Is tone and depth right for {audience}?
2. OBJECTIVE ALIGNMENT — Does every slide serve the objective?
3. NARRATIVE FLOW — Is there a coherent story from start to finish?
4. CONTENT COMPLETENESS — Are bullets specific, not vague?
5. SLIDE BALANCE — Is content well distributed?
6. OPENING AND CLOSING — Strong title slide, clear next steps at the end?

Return a JSON object with:
- passes: boolean (true only if ALL checks pass)
- score: float 0.0-1.0
- issues: flat list of strings, each issue is a single string (empty list if passes)
- fixes_required: flat list of strings, each fix is a single string (empty list if passes)

IMPORTANT: issues and fixes_required must be flat arrays of strings only.
No nested arrays. No objects. Each element must be a plain string.

Return only valid JSON. No explanation.
"""

class VerificationAgent:
    def __init__(self):
        self.llm = ChatOllama(
            model="deepseek-r1:8b",
            base_url="http://localhost:11434",
            format="json",
            temperature=0.0
        )

    def run(self, intent: IntentOutput, storyboard: StoryboardOutput) -> VerificationOutput:
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