from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from models.schemas import IntentOutput, PresentationType
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
- If the user's message contains inline data (CSV rows, tables, numbers), 
  set "contains_user_data" to true in your response.
  
Return only valid JSON. No explanation.
"""

class IntentAgent:
    def __init__(self):
        self.llm = ChatOllama(
            model="gemma4:e4b",
            base_url="http://localhost:11434",
            format="json",
            temperature=0.1
        )

    def run(self, prompt: str) -> IntentOutput:
        chain = ChatPromptTemplate.from_template(PROMPT) | self.llm
        result = chain.invoke({"prompt": prompt})
        return IntentOutput(**json.loads(result.content))
    