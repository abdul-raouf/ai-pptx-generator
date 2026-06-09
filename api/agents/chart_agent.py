from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from models.schemas import StoryboardOutput
import json

ASSESSMENT_PROMPT = """
You are reviewing a presentation storyboard to identify which slides need charts.

STORYBOARD:
{storyboard_json}

A slide needs a chart if:
- Its slide_type is "data"
- Its key_message or bullets reference specific numbers, trends, or comparisons
- A visual would materially help the audience understand the data

Return a JSON array of slide indices (integers) that need charts.
Example: [2, 5, 8]
Return only valid JSON. No explanation.
"""

CHART_TYPE_PROMPT = """
A user has provided the following data for a chart:

Data:
{data_preview}

Slide context: {slide_context}

Based on this data, recommend the best chart type and explain why in one sentence.

Rules:
- Use "bar" for comparing categories or discrete values
- Use "line" for trends over time
- Use "pie" for part-to-whole relationships (max 6 categories)
- Use "scatter" for correlation between two numeric variables

Return a JSON object with:
- chart_type: one of "bar", "line", "pie", "scatter"
- reason: one sentence justification

Return only valid JSON. No explanation.
"""

class ChartAgent:
    def __init__(self):
        self.llm = ChatOllama(
            model="deepseek-r1:8b",
            base_url="http://localhost:11434",
            format="json",
            temperature=0.0
        )

    def identify_chart_slides(self, storyboard: StoryboardOutput) -> list[int]:
        storyboard_json = json.dumps([
            {
                "index": s.slide_index,
                "title": s.slide_title,
                "type": s.slide_type,
                "key_message": s.key_message,
                "bullets": s.bullet_points
            }
            for s in storyboard.slides
        ], indent=2)

        chain = ChatPromptTemplate.from_template(ASSESSMENT_PROMPT) | self.llm
        result = chain.invoke({"storyboard_json": storyboard_json})
        raw = json.loads(result.content)

        # LLM may return a bare list ([1, 3]) or a dict ({ "indices": [1, 3] })
        if isinstance(raw, dict):
            raw = raw.get("indices", raw.get("slide_indices", []))
        return [i for i in raw if isinstance(i, int)]

    def recommend_chart_type(self, data_preview: str, slide_context: str) -> dict:
        chain = ChatPromptTemplate.from_template(CHART_TYPE_PROMPT) | self.llm
        result = chain.invoke({
            "data_preview": data_preview[:1000],
            "slide_context": slide_context
        })
        return json.loads(result.content)