import json
import logging
import re
import time
from typing import Dict, Any, List, Optional
from langchain_core.messages import SystemMessage, HumanMessage
from backend.app.config import settings

logger = logging.getLogger("VideoTutor.Evaluator")

EVALUATOR_JUDGE_PROMPT = """
You are an expert AI Quality & Evaluation Judge for an educational Video Tutor platform.
Your task is to strictly evaluate the LLM's generated response based on the student's request, the system prompt instructions, and the retrieved video transcript context.
*IMPORTANT:* Do not penalize the AI (in Relevance or Verdict) for lacking conversational confirmation (e.g. "I have updated the notes") if the actual requested task was successfully completed in the output.

### Context (Video Transcript Chunk):
{retrieval_context}

### System Prompt Instructions Given to Model:
{system_prompt}

### Student Question:
{user_request}

### LLM Generated Answer:
{actual_output}

### Evaluation Criteria:
1. **faithfulness_score** (0.0 to 1.0): Are the factual claims made in the answer strictly supported by the Video Transcript Context without hallucination? If context is not applicable (general knowledge), rate factual correctness.
2. **prompt_adherence_score** (0.0 to 1.0): Did the LLM follow the structure, tone, and directives defined in the System Prompt?
3. **answer_relevance_score** (0.0 to 1.0): Does the response directly and comprehensively address the student's question?
4. **prompt_quality_score** (0.0 to 1.0): Is the System Prompt well-structured, clear, and appropriate for guiding the AI to answer the student's question?
5. **retrieval_quality_score** (0.0 to 1.0): Does the retrieved Video Transcript Context contain the correct and sufficient information to answer the student's question?
6. **hallucination_detected** (boolean): True if the LLM fabricated specific facts, claims, or false timestamps.

Output ONLY a single valid JSON object. You MUST provide your reasoning BEFORE the score to ensure Chain-of-Thought logic. Use this exact schema (no markdown, no other text):
{{
  "faithfulness_reasoning": "Explanation for faithfulness...",
  "faithfulness_score": 0.95,
  "prompt_adherence_reasoning": "Explanation for adherence...",
  "prompt_adherence_score": 0.98,
  "answer_relevance_reasoning": "Explanation for relevance...",
  "answer_relevance_score": 0.95,
  "prompt_quality_reasoning": "Explanation for prompt quality...",
  "prompt_quality_score": 0.90,
  "retrieval_quality_reasoning": "Explanation for retrieval quality...",
  "retrieval_quality_score": 0.85,
  "hallucination_detected": false,
  "verdict": "PASSED",
  "reasoning": "Overall 1-sentence summary verdict."
}}
"""


def evaluate_prompt_quality(prompt_template: str, required_variables: Optional[List[str]] = None) -> Dict[str, Any]:
    """Static Prompt Quality Linter:
    Verifies that a prompt template has all required variables, clear structure, and negative constraints.
    """
    if not prompt_template or not isinstance(prompt_template, str):
        return {
            "is_valid": False,
            "quality_score": 0.0,
            "missing_variables": required_variables or [],
            "issues": ["Prompt template is empty or invalid."]
        }

    issues = []
    missing_vars = []

    if required_variables:
        for var in required_variables:
            placeholder = f"{{{var}}}"
            if placeholder not in prompt_template:
                missing_vars.append(var)
                issues.append(f"Missing required placeholder: {placeholder}")

    has_structure = bool(re.search(r"(#|format|instruction|guideline|rule)", prompt_template, re.IGNORECASE))
    if not has_structure:
        issues.append("Prompt lacks clear structural section headers.")

    score = 1.0
    if missing_vars:
        score -= (len(missing_vars) * 0.3)
    if issues:
        score -= (len(issues) * 0.1)

    score = max(0.0, min(1.0, round(score, 2)))

    return {
        "is_valid": len(missing_vars) == 0,
        "quality_score": score,
        "missing_variables": missing_vars,
        "issues": issues,
        "char_count": len(prompt_template)
    }


def evaluate_faithfulness(actual_output: str, retrieval_context: str) -> float:
    """Calculates factual grounding between answer and transcript context."""
    if not actual_output:
        return 0.0
    if not retrieval_context:
        # If no transcript retrieval was performed (e.g. general knowledge), return neutral 0.90
        return 0.90

    out_words = set(re.findall(r"\b[a-zA-Z]{4,}\b", actual_output.lower()))
    ctx_words = set(re.findall(r"\b[a-zA-Z]{4,}\b", retrieval_context.lower()))

    if not out_words:
        return 1.0

    overlap = len(out_words.intersection(ctx_words))
    ratio = overlap / min(len(out_words), len(ctx_words) + 1)
    
    score = min(1.0, 0.70 + (ratio * 0.35))
    return round(score, 2)


def evaluate_prompt_adherence(actual_output: str, system_prompt: str) -> float:
    """Checks if the output followed the formatting constraints in the system prompt."""
    if not actual_output:
        return 0.0

    score = 1.0
    if "#" in system_prompt and "#" not in actual_output:
        score -= 0.15

    if ("- " in system_prompt or "bullet" in system_prompt.lower()) and "- " not in actual_output:
        score -= 0.10

    return max(0.5, min(1.0, round(score, 2)))


def evaluate_retrieval_quality(retrieval_context: str, user_request: str) -> Dict[str, Any]:
    """Evaluates the quality of retrieved transcript chunks against the user's question.
    
    Checks:
    1. Whether any context was retrieved at all (empty retrieval = low score)
    2. Keyword overlap between the user's question and retrieved chunks
    3. Context length adequacy (too short = insufficient grounding)
    
    Returns:
        {"retrieval_score": float, "is_empty": bool, "context_length": int, "keyword_overlap": float}
    """
    if not retrieval_context or len(retrieval_context.strip()) < 10:
        return {
            "retrieval_score": 0.0,
            "is_empty": True,
            "context_length": 0,
            "keyword_overlap": 0.0
        }

    query_words = set(re.findall(r"\b[a-zA-Z]{4,}\b", user_request.lower()))
    ctx_words = set(re.findall(r"\b[a-zA-Z]{4,}\b", retrieval_context.lower()))

    if not query_words:
        return {
            "retrieval_score": 0.85,
            "is_empty": False,
            "context_length": len(retrieval_context),
            "keyword_overlap": 0.0
        }

    overlap = len(query_words.intersection(ctx_words))
    keyword_overlap = overlap / len(query_words) if query_words else 0.0

    score = min(1.0, 0.50 + (keyword_overlap * 0.50))

    if len(retrieval_context) > 500:
        score = min(1.0, score + 0.05)

    return {
        "retrieval_score": round(score, 2),
        "is_empty": False,
        "context_length": len(retrieval_context),
        "keyword_overlap": round(keyword_overlap, 2)
    }


def evaluate_answer_relevance(actual_output: str, user_request: str) -> float:
    """Evaluates whether the LLM's answer directly addresses the user's question.
    
    Uses keyword overlap between question and answer, plus structural checks
    (does the answer reference the question's key terms?).
    
    Returns:
        float score between 0.0 and 1.0
    """
    if not actual_output or not user_request:
        return 0.0

    q_words = set(re.findall(r"\b[a-zA-Z]{4,}\b", user_request.lower()))
    a_words = set(re.findall(r"\b[a-zA-Z]{4,}\b", actual_output.lower()))

    if not q_words:
        return 0.90  # Short/vague question, can't measure well

    overlap = len(q_words.intersection(a_words))
    coverage = overlap / len(q_words)

    score = min(1.0, 0.50 + (coverage * 0.50))

    if len(actual_output) > 200:
        score = min(1.0, score + 0.05)

    return round(score, 2)


def evaluate_llm_interaction(
    user_request: str,
    actual_output: str,
    retrieval_context: str = "",
    system_prompt: str = "",
    use_llm_judge: bool = True
) -> Dict[str, Any]:
    """Generates a comprehensive Multi-Dimensional Evaluation Scorecard.
    Uses LLM-as-a-Judge if available, with robust deterministic fallback.
    
    Returns:
        scorecard: {
            "faithfulness_score": float (0.0 - 1.0),
            "prompt_adherence_score": float (0.0 - 1.0),
            "answer_relevance_score": float (0.0 - 1.0),
            "overall_quality_score": float (0.0 - 1.0),
            "hallucination_detected": bool,
            "verdict": "PASSED" | "WARNING" | "FAILED",
            "reasoning": str
        }
    """
    if not actual_output or len(actual_output.strip()) == 0:
        return {
            "faithfulness_score": 0.0,
            "prompt_adherence_score": 0.0,
            "answer_relevance_score": 0.0,
            "overall_quality_score": 0.0,
            "hallucination_detected": True,
            "verdict": "FAILED",
            "reasoning": "Output was empty."
        }

    if use_llm_judge:
        try:
            from backend.app.agent.nodes import get_llm, clean_think_tags
            judge_llm = get_llm()
            if judge_llm is not None:
                formatted_judge_prompt = EVALUATOR_JUDGE_PROMPT.format(
                    retrieval_context=retrieval_context[:3000] if retrieval_context else "(No transcript retrieved - General Knowledge query)",
                    system_prompt=system_prompt[:2000] if system_prompt else "(Standard Video Tutor Prompt)",
                    user_request=user_request,
                    actual_output=actual_output[:3000]
                )

                resp = judge_llm.invoke([
                    SystemMessage(content="You are a strict, impartial AI evaluation judge. Return ONLY valid JSON."),
                    HumanMessage(content=formatted_judge_prompt)
                ])

                content = clean_think_tags(resp.content if isinstance(resp.content, str) else str(resp.content))
                match = re.search(r"\{.*?\}", content, re.DOTALL)
                if match:
                    parsed = json.loads(match.group(0))
                    f_score = float(parsed.get("faithfulness_score", 0.95))
                    p_score = float(parsed.get("prompt_adherence_score", 0.95))
                    r_score = float(parsed.get("answer_relevance_score", 0.95))
                    
                    f_reasoning = parsed.get("faithfulness_reasoning", "Evaluated by LLM.")
                    p_reasoning = parsed.get("prompt_adherence_reasoning", "Evaluated by LLM.")
                    r_reasoning = parsed.get("answer_relevance_reasoning", "Evaluated by LLM.")
                    ret_reasoning = parsed.get("retrieval_quality_reasoning", "Evaluated by LLM.")
                    pq_reasoning = parsed.get("prompt_quality_reasoning", "Evaluated by LLM.")

                    overall = round((f_score * 0.4) + (p_score * 0.3) + (r_score * 0.3), 2)
                    is_halluc = bool(parsed.get("hallucination_detected", False))
                    raw_verdict = parsed.get("verdict", "").upper()
                    
                    if is_halluc or f_score < 0.65:
                        verdict = "WARNING" if overall >= 0.50 else "FAILED"
                    elif raw_verdict in ["PASSED", "WARNING", "FAILED"]:
                        verdict = raw_verdict
                    else:
                        verdict = "PASSED" if overall >= 0.75 else "WARNING" if overall >= 0.50 else "FAILED"

                    reasoning_text = parsed.get("reasoning", "LLM-as-a-Judge completed evaluation successfully.")
                    
                    # Calculate deterministic base, then override the main scores with the LLM's judgement
                    retrieval_eval = evaluate_retrieval_quality(retrieval_context, user_request)
                    if "retrieval_quality_score" in parsed:
                        retrieval_eval["retrieval_score"] = float(parsed["retrieval_quality_score"])
                    retrieval_eval["reasoning"] = ret_reasoning

                    prompt_eval = evaluate_prompt_quality(system_prompt) if system_prompt else None
                    if prompt_eval and "prompt_quality_score" in parsed:
                        prompt_eval["quality_score"] = float(parsed["prompt_quality_score"])
                        prompt_eval["reasoning"] = pq_reasoning

                    logger.info(
                        f"[LLM-as-a-Judge] Evaluated successfully -> "
                        f"Faithfulness: {int(f_score*100)}%, Adherence: {int(p_score*100)}%, "
                        f"Relevance: {int(r_score*100)}%, Retrieval: {int(retrieval_eval['retrieval_score']*100)}%, "
                        f"Prompt Quality: {int(prompt_eval['quality_score']*100) if prompt_eval else '—'}%, "
                        f"Verdict: {verdict}. Reasoning: {reasoning_text}"
                    )

                    return {
                        "evaluator_type": "LLM_AS_A_JUDGE",
                        "faithfulness_score": f_score,
                        "prompt_adherence_score": p_score,
                        "answer_relevance_score": r_score,
                        "faithfulness_reasoning": f_reasoning,
                        "prompt_adherence_reasoning": p_reasoning,
                        "answer_relevance_reasoning": r_reasoning,
                        "overall_quality_score": overall,
                        "hallucination_detected": is_halluc,
                        "verdict": verdict,
                        "retrieval_quality": retrieval_eval,
                        "prompt_quality": prompt_eval,
                        "reasoning": reasoning_text
                    }
        except Exception as e:
            logger.warning(f"LLM-as-a-Judge invocation failed ({e}). Falling back to deterministic evaluation.")

    f_score = evaluate_faithfulness(actual_output, retrieval_context)
    p_score = evaluate_prompt_adherence(actual_output, system_prompt)
    r_score = evaluate_answer_relevance(actual_output, user_request)
    retrieval_eval = evaluate_retrieval_quality(retrieval_context, user_request)
    prompt_eval = evaluate_prompt_quality(system_prompt) if system_prompt else None
    overall = round((f_score * 0.4) + (p_score * 0.3) + (r_score * 0.3), 2)
    is_halluc = f_score < 0.60
    verdict = "PASSED" if overall >= 0.75 and not is_halluc else "WARNING" if overall >= 0.50 else "FAILED"

    logger.info(
        f"[Deterministic Engine] Evaluated -> Faithfulness: {int(f_score*100)}%, "
        f"Adherence: {int(p_score*100)}%, Relevance: {int(r_score*100)}%, "
        f"Retrieval: {int(retrieval_eval['retrieval_score']*100)}%, "
        f"Prompt Quality: {int(prompt_eval['quality_score']*100) if prompt_eval else '—'}%"
    )

    retrieval_eval["reasoning"] = "Evaluated deterministically (keyword overlap)."
    if prompt_eval:
        prompt_eval["reasoning"] = "Evaluated deterministically (regex structure)."

    return {
        "evaluator_type": "DETERMINISTIC_ENGINE",
        "faithfulness_score": f_score,
        "prompt_adherence_score": p_score,
        "answer_relevance_score": r_score,
        "faithfulness_reasoning": "Evaluated deterministically based on context overlap.",
        "prompt_adherence_reasoning": "Evaluated deterministically via format heuristic.",
        "answer_relevance_reasoning": "Evaluated deterministically based on query coverage.",
        "overall_quality_score": overall,
        "hallucination_detected": is_halluc,
        "verdict": verdict,
        "retrieval_quality": retrieval_eval,
        "prompt_quality": prompt_eval,
        "reasoning": (
            f"Evaluated via deterministic metric engine "
            f"(Faithfulness: {int(f_score*100)}%, Adherence: {int(p_score*100)}%, "
            f"Relevance: {int(r_score*100)}%, Retrieval: {int(retrieval_eval['retrieval_score']*100)}%)."
        )
    }
