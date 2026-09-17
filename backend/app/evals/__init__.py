"""VideoTutor AI - LLM Evaluation & Guardrails Module.
Provides multi-dimensional LLM evaluation (Faithfulness, Grounding, Prompt Adherence, Quality)
and deterministic Input/Output Guardrails.
"""

from backend.app.evals.guardrails import check_input_guardrails, check_output_guardrails
from backend.app.evals.evaluator import (
    evaluate_llm_interaction,
    evaluate_prompt_quality,
    evaluate_faithfulness,
    evaluate_prompt_adherence,
    evaluate_retrieval_quality,
    evaluate_answer_relevance,
)

__all__ = [
    "check_input_guardrails",
    "check_output_guardrails",
    "evaluate_llm_interaction",
    "evaluate_prompt_quality",
    "evaluate_faithfulness",
    "evaluate_prompt_adherence",
    "evaluate_retrieval_quality",
    "evaluate_answer_relevance",
]

