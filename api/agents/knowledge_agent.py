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
Slide count: {estimated_slides}

Honestly assess your own knowledge before building:

1. Do you have sufficient, accurate knowledge to populate {estimated_slides} slides on this topic for this audience at this depth?
2. What aspects do you know well?
3. What aspects are you uncertain about?
4. If insufficient, what are the 1-3 most important clarifying questions to ask the user?
5. After questions, would you still need the user to paste reference text?

Return a JSON object with:
- is_sufficient: boolean
- confidence: float 0.0-1.0
- known_aspects: list of strings
- unknown_aspects: list of strings
- clarifying_questions: list of strings, max 3 (empty if sufficient)
- needs_user_context: boolean

Return only valid JSON. No explanation.
"""

class KnowledgeAssessmentAgent:
    def __init__(self):
        self.llm = ChatOllama(
            model="qwen3.6:27b",
            base_url="http://localhost:11434",
            format="json",
            temperature=0.1
        )

    def run(self, intent: IntentOutput) -> KnowledgeAssessmentOutput:
        # print(PROMPT)
        chain = ChatPromptTemplate.from_template(PROMPT) | self.llm
        result = chain.invoke(intent.model_dump())
        return KnowledgeAssessmentOutput(**json.loads(result.content))