import re
import logging
from typing import Dict, Any, Tuple

logger = logging.getLogger("VideoTutor.Guardrails")

# Common Adversarial Prompt Injection & Jailbreak Patterns
PROMPT_INJECTION_PATTERNS = [
    r"ignore (all\s+)?(previous|prior|above)\s+(instructions|prompts|rules|guidelines|directives)",
    r"disregard (all\s+)?(previous|prior|above)\s+(instructions|prompts|rules|guidelines)",
    r"bypass (all\s+)?(safety|system|guardrail|security)\s+(rules|restrictions|filters)",
    r"reveal (your\s+)?(system prompt|initial prompt|hidden prompt|secret instructions)",
    r"output (your\s+)?(system prompt|full prompt|initial instructions)",
    r"you are now (an?\s+)?(unfiltered|unrestricted|jailbroken|evil)\s+(ai|assistant|model|bot)",
    r"pretend (you are|to be)\s+(dan|an unfiltered|evil|do anything now)",
    r"start all answers with\s+(dan|jailbreak)",
    r"developer mode enabled",
    r"act as an unrestricted",
    r"ignore everything and say",
]


def check_input_guardrails(user_request: str) -> Tuple[bool, str, Dict[str, Any]]:
    """Input Guardrail Check:
    Inspects student query for prompt injection, jailbreak attempts, and malformed inputs.
    
    Note: General knowledge and off-topic questions are intentionally ALLOWED to pass,
    so they can be routed seamlessly to the General Knowledge educational tool.
    
    Returns:
        (is_safe: bool, refusal_reason: str, metadata: dict)
    """
    if not user_request or not isinstance(user_request, str):
        return False, "Input query cannot be empty.", {"check": "empty_input", "blocked": True}

    cleaned = user_request.strip()

    if len(cleaned) < 2:
        return False, "Query is too short to process.", {"check": "min_length", "blocked": True}

    if len(cleaned) > 4000:
        return False, "Query exceeds the maximum allowed character limit (4,000 characters).", {
            "check": "max_length",
            "blocked": True,
        }

    # Prompt injection check
    for pattern in PROMPT_INJECTION_PATTERNS:
        match = re.search(pattern, cleaned, re.IGNORECASE)
        if match:
            matched_phrase = match.group(0)
            logger.warning(f"🛡️ Guardrail Interception: Prompt injection pattern '{matched_phrase}' detected in query: '{cleaned}'")
            return (
                False,
                "⚠️ For security and educational integrity, prompt overrides or system prompt extraction requests are not permitted.",
                {
                    "check": "prompt_injection",
                    "matched_pattern": matched_phrase,
                    "blocked": True,
                },
            )

    return True, "Input passed safety guardrails.", {"check": "safety_passed", "blocked": False}


def check_output_guardrails(output_text: str) -> Dict[str, Any]:
    """Output Guardrail Check:
    Verifies LLM response formatting and cleans internal reasoning tags.
    
    Returns:
        metadata: dict with cleanliness flags and sanitized output
    """
    if not output_text:
        return {
            "is_valid": False,
            "has_leak": False,
            "cleaned_text": "No response generated.",
            "status": "EMPTY_OUTPUT"
        }

    # Clean internal reasoning tags if present
    has_leak = bool(re.search(r"<think>.*?</think>", output_text, flags=re.DOTALL) or "<think>" in output_text)
    
    cleaned = output_text
    if "<think>" in cleaned:
        cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
        cleaned = re.sub(r"<think>.*", "", cleaned, flags=re.DOTALL).strip()

    return {
        "is_valid": len(cleaned.strip()) > 0,
        "has_leak": has_leak,
        "cleaned_text": cleaned,
        "status": "PASSED" if len(cleaned.strip()) > 0 else "EMPTY"
    }
