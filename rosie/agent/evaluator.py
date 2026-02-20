import json
import logging
from ..llm.backend import get_llm

logger = logging.getLogger(__name__)

EVAL_PROMPT = """You are an LLM judge evaluating the quality of an AI response about an AWS environment.

Question: {question}
Response: {response}

Score the response 1-5 on:
1. Accuracy (does it correctly address the question?)
2. Completeness (does it include relevant details like resource IDs?)
3. Clarity (is it clear and actionable?)

Return a JSON object with keys: accuracy, completeness, clarity, overall, reasoning.
JSON only, no markdown."""

def evaluate(question: str, response: str, provider: str | None = None) -> dict:
    llm = get_llm(provider=provider)
    prompt = EVAL_PROMPT.format(question=question, response=response)
    try:
        result = llm.invoke(prompt)
        content = result.content if hasattr(result, "content") else str(result)
        return json.loads(content)
    except Exception as e:
        logger.warning(f"Evaluation failed: {e}")
        return {"accuracy": 0, "completeness": 0, "clarity": 0, "overall": 0, "reasoning": str(e)}
