from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from io import StringIO
import pandas as pd
import json

PROMPT = """
You are a data analyst. The user has provided raw data that needs to be prepared 
for chart generation.

RAW DATA:
{raw_data}

CHART CONTEXT (what this chart is for):
{slide_context}

Your job:
1. Parse the raw data regardless of its format — CSV, space-separated, 
   table, or informal text.
2. Identify the most meaningful columns for visualising in the context of 
   the slide. Do not include all columns — pick the 2-3 most relevant.
3. If the data needs aggregation (e.g. total sales per brand, count per city), 
   perform it. Return aggregated data, not raw rows.
4. Return clean, chart-ready data.

Return a JSON object with:
- columns: list of column name strings (first column is the category/label, 
  rest are numeric values)
- rows: list of row arrays matching the columns order
- suggested_title: a short chart title based on the data and context
- notes: one sentence explaining what you did to the data (e.g. aggregated by brand)

Example output:
{{
  "columns": ["CarBrand", "TotalRevenue"],
  "rows": [
    ["Toyota", 590000],
    ["Honda", 506000],
    ["Tesla", 740000]
  ],
  "suggested_title": "Total Revenue by Car Brand",
  "notes": "Aggregated TotalAmount by CarBrand across all sales records."
}}

Return only valid JSON. No explanation outside the JSON.
"""



class DataParsingAgent :
    def __init__(self):
        self.llm = ChatOllama(
            model = "deepseek-r1:8b",
            base_url="http://localhost:11434",
            format="json",
            temperature=0.0
        )
    def run(self, raw_data:str, slide_context:str) -> pd.DataFrame:
        chain = ChatPromptTemplate.from_template(PROMPT) | self.llm
        result = chain.invoke({
            "raw_data" : raw_data[:4000],
            "slide_context" : slide_context
        })
        
        try:
            parsed = json.loads(result.content)
            df = pd.DataFrame(parsed["rows"], columns=parsed["columns"])
            return df, parsed.get("suggested_title", ""), parsed.get("notes", "")
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            raise RuntimeError(f"DataParsingAgent: LLM did not return valid JSON – {type(e).__name__}: {e}") from e
        except Exception as e:
            raise RuntimeError(f"DataParsingAgent: failed to build DataFrame – {type(e).__name__}: {e}") from e

       