import json
import logging
import re
import time
from typing import Dict, Any, List
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from backend.app.config import settings
from backend.app.prompts.learning import (
    SYSTEM_PROMPT,
    INTENT_CLASSIFICATION_PROMPT,
    WHOLE_VIDEO_STUDY_NOTES_PROMPT,
    WHOLE_VIDEO_QA_PROMPT,
    SPECIFIC_TOPIC_EXPLAIN_PROMPT,
    GENERAL_KNOWLEDGE_PROMPT,
    NOTES_REVISION_PROMPT,
)
from backend.app.mcp.client import mcp_client
from backend.app.agent.state import AgentState
from backend.app.evals.guardrails import check_input_guardrails, check_output_guardrails
from backend.app.evals.evaluator import evaluate_llm_interaction

logger = logging.getLogger("VideoTutor.AgentNodes")


def clean_think_tags(text: str) -> str:
    """Remove internal reasoning tags and meta-thinking from reasoning models (e.g. Qwen, DeepSeek)."""
    if not isinstance(text, str):
        return str(text)

    cleaned = text.strip()

    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()

    if "<think>" in cleaned:
        if "</think>" in cleaned:
            cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
        else:
            header_match = re.search(r"(#+\s+.*)", cleaned, re.DOTALL)
            if header_match:
                cleaned = header_match.group(1).strip()
            else:
                cleaned = re.sub(r"<think>.*", "", cleaned, flags=re.DOTALL).strip()

    cleaned = re.sub(
        r"^(Here'?s a thinking process:.*?(\n\n|# ))",
        r"\2",
        cleaned,
        flags=re.DOTALL | re.IGNORECASE,
    ).strip()
    return cleaned


def get_llm():
    """Factory to initialize configured LLM based on environment settings."""
    api_key_groq = settings.GROQ_API_KEY
    api_key_google = settings.GOOGLE_API_KEY
    api_key_openai = settings.OPENAI_API_KEY

    if api_key_groq and api_key_groq != "mock_key_for_dev":
        try:
            from langchain_groq import ChatGroq
            logger.info(f"Initializing ChatGroq (Model: {settings.GROQ_MODEL})...")
            return ChatGroq(
                model=settings.GROQ_MODEL,
                groq_api_key=api_key_groq,
                temperature=0.2,
                max_tokens=1500,
            )
        except Exception as e:
            logger.warning(f"Could not initialize Groq LLM: {e}")

    if api_key_google and api_key_google != "mock_key_for_dev":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            logger.info("Initializing ChatGoogleGenerativeAI (Gemini)...")
            return ChatGoogleGenerativeAI(
                model=settings.LLM_MODEL,
                google_api_key=api_key_google,
                temperature=0.2,
                max_output_tokens=6000,
            )
        except Exception as e:
            logger.warning(f"Could not initialize Google Gemini LLM: {e}")

    if api_key_openai and api_key_openai != "mock_key_for_dev":
        try:
            from langchain_openai import ChatOpenAI
            logger.info("Initializing ChatOpenAI...")
            return ChatOpenAI(
                model=settings.LLM_MODEL,
                openai_api_key=api_key_openai,
                temperature=0.2,
                max_tokens=6000,
            )
        except Exception as e:
            logger.warning(f"Could not initialize OpenAI LLM: {e}")

    return None


def analyze_query_intent_with_llm(llm, user_request: str, video_id: str) -> Dict[str, Any]:
    """Intelligent Query Understanding: Uses the LLM to classify user intent and extract search keywords dynamically."""
    if not llm or not user_request:
        return _heuristic_intent_classification(user_request)

    intent_prompt = INTENT_CLASSIFICATION_PROMPT.format(video_id=video_id, user_request=user_request)
    try:
        resp = llm.invoke([
            SystemMessage(content="You are an intent classification and query understanding engine for an AI Video Tutor. Analyze the user request and return ONLY the JSON object."),
            HumanMessage(content=intent_prompt)
        ])
        content = clean_think_tags(resp.content if isinstance(resp.content, str) else str(resp.content))
        match = re.search(r"\{.*?\}", content, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            logger.info(f"LLM Dynamic Intent Classification: {parsed}")
            return parsed
    except Exception as e:
        logger.warning(f"LLM Intent Classification failed: {e}")

    return _heuristic_intent_classification(user_request)


def _heuristic_intent_classification(user_request: str) -> Dict[str, Any]:
    """Fallback heuristic classifier when LLM is unavailable or unparsed."""
    req_l = (user_request or "").lower()
    if any(k in req_l for k in ["quiz", "test", "question", "summary", "note", "takeaway", "timeline", "overview", "cheat"]):
        return {"intent": "whole_video", "search_keyword": ""}
    return {"intent": "specific_search", "search_keyword": user_request}


def agent_node(state: AgentState) -> Dict[str, Any]:
    """Agent Reasoning Node: Evaluates conversation state, understands intent, and decides next action or response."""
    messages = state.get("messages", [])
    video_id = state.get("video_id", "")
    user_request = state.get("user_request", "")

    # 1. Deterministic Input Guardrail Check (Prompt Injection / Safety)
    is_safe, refusal_reason, guard_meta = check_input_guardrails(user_request)
    if not is_safe:
        logger.warning(f"🛡️ Guardrail Interception in agent_node: {refusal_reason}")
        refusal_msg = f"{refusal_reason}"
        eval_scorecard = {
            "faithfulness_score": 0.0,
            "prompt_adherence_score": 1.0,
            "answer_relevance_score": 0.0,
            "overall_quality_score": 1.0,
            "hallucination_detected": False,
            "verdict": "BLOCKED_BY_GUARDRAIL",
            "reasoning": f"Input guardrail blocked adversarial request: {guard_meta.get('matched_pattern', 'restricted_input')}"
        }
        return {
            "messages": [AIMessage(content=refusal_msg)],
            "retrieved_chunks": [],
            "final_response": refusal_msg,
            "intent": "blocked_by_guardrail",
            "search_query": user_request,
            "executed_tools": [],
            "guardrail_status": guard_meta,
            "eval_scorecard": eval_scorecard,
            "is_blocked": True,
            "llm_latency_ms": 0.0,
            "intent_latency_ms": 0.0,
            "tool_latency_ms": 0.0,
            "token_usage": {},
            "active_model": "guardrail-shield",
        }

    system_prompt = SYSTEM_PROMPT
    if video_id:
        system_prompt += f"\n\nCURRENT ACTIVE VIDEO ID: {video_id}\nUse video_id='{video_id}' when executing transcript tools."

    if not messages:
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_request)]
    elif not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=system_prompt)] + list(messages)
    else:
        messages[0] = SystemMessage(content=system_prompt)

    llm = get_llm()

    req_lower = (user_request or "").lower()
    whole_video_keywords = [
        "note", "study", "summary", "guide", "timeline", "overview", "cheat", "quiz", 
        "test", "takeaway", "moto", "motto", "purpose", "goal", "theme", 
        "gist", "main point", "main idea", "explain video", "what is this video", 
        "what is the video", "what does this video", "what this video", "what video"
    ]
    is_whole_video_req = any(re.search(rf"\b{w}\b", req_lower) for w in whole_video_keywords)

    intent_start_t = time.time()
    if is_whole_video_req:
        intent = "whole_video"
        search_kw = ""
        intent_latency_ms = 0.0
    else:
        intent_data = analyze_query_intent_with_llm(llm, user_request, video_id)
        intent = intent_data.get("intent", "specific_search")
        search_kw = intent_data.get("search_keyword", "").strip() or user_request
        intent_latency_ms = round((time.time() - intent_start_t) * 1000, 1)

    if intent == "whole_video":
        logger.info(f"Intent classified as 'whole_video'. Retrieving multi-section timeline for video '{video_id}'...")
        tool_start_t = time.time()
        notes_res = mcp_client.execute_tool("generate_video_notes", video_id=video_id)
        tool_latency_ms = round((time.time() - tool_start_t) * 1000, 1)

        chunks = notes_res.get("chunks", [])
        combined_text = "\n\n".join(
            f"[{int(c.get('start_time', 0))//60:02d}:{int(c.get('start_time', 0))%60:02d}] {c.get('text', '')}"
            for c in chunks
        )

        req_lower = user_request.lower()
        if any(w in req_lower for w in ["note", "guide", "study", "summary"]):
            sys_inst = WHOLE_VIDEO_STUDY_NOTES_PROMPT.format(video_id=video_id, combined_transcript=combined_text)
        else:
            sys_inst = WHOLE_VIDEO_QA_PROMPT.format(user_request=user_request, video_id=video_id, combined_transcript=combined_text)

        final_content = None
        token_usage = {}
        active_model = "compound-beta-mini"
        llm_start_t = time.time()
        if llm is not None:
            try:
                llm_out = llm.invoke([
                    SystemMessage(content=sys_inst),
                    HumanMessage(content=user_request)
                ])
                final_content = clean_think_tags(llm_out.content if isinstance(llm_out.content, str) else str(llm_out.content))
                meta = getattr(llm_out, "response_metadata", {}) or {}
                token_usage = meta.get("token_usage", {})
                active_model = meta.get("model_name") or getattr(llm, "model_name", "compound-beta-mini")
            except Exception as ex:
                logger.warning(f"LLM whole-video synthesis failed: {ex}. Attempting fallback with compound-beta-mini...")
                try:
                    from langchain_groq import ChatGroq
                    fallback_llm = ChatGroq(model="compound-beta-mini", groq_api_key=settings.GROQ_API_KEY, temperature=0.2, max_tokens=1500)
                    llm_out = fallback_llm.invoke([
                        SystemMessage(content=sys_inst),
                        HumanMessage(content=user_request)
                    ])
                    final_content = clean_think_tags(llm_out.content if isinstance(llm_out.content, str) else str(llm_out.content))
                    meta = getattr(llm_out, "response_metadata", {}) or {}
                    token_usage = meta.get("token_usage", {})
                    active_model = "compound-beta-mini"
                except Exception as ex2:
                    logger.warning(f"Fallback LLM also failed: {ex2}")
        llm_duration_ms = round((time.time() - llm_start_t) * 1000, 1)

        if not final_content:
            final_content = (
                f"#  Study Notes: Video Overview ({video_id})\n\n"
                f"##  Executive Summary\n"
                f"This lecture provides an in-depth breakdown of key concepts and architectures explained with real-world examples.\n\n"
                f"---\n\n"
                f"## Lecture Milestones\n"
                + "\n".join(
                    f"- **[{int(c.get('start_time', 0))//60:02d}:{int(c.get('start_time', 0))%60:02d}](https://www.youtube.com/watch?v={video_id}&t={int(c.get('start_time', 0))})**: {c.get('text', '')[:120]}..."
                    for c in chunks[:6]
                )
            )

        # Output Guardrails & Multi-Dimensional Evaluation
        out_guard = check_output_guardrails(final_content)
        sanitized_response = out_guard["cleaned_text"]
        eval_scorecard = evaluate_llm_interaction(
            user_request=user_request,
            actual_output=sanitized_response,
            retrieval_context=combined_text,
            system_prompt=sys_inst,
            use_llm_judge=True
        )

        is_notes = "note" in req_lower or "# " in sanitized_response
        return {
            "messages": [AIMessage(content=sanitized_response)],
            "retrieved_chunks": chunks,
            "notes": sanitized_response if is_notes else None,
            "requires_human_approval": is_notes,
            "final_response": sanitized_response,
            "prompt_sent": sys_inst,
            "intent": intent,
            "search_query": user_request,
            "executed_tools": [{"name": "generate_video_notes", "args": {"video_id": video_id}}],
            "guardrail_status": {"input": guard_meta, "output": out_guard},
            "eval_scorecard": eval_scorecard,
            "is_blocked": False,
            "llm_latency_ms": llm_duration_ms,
            "intent_latency_ms": intent_latency_ms,
            "tool_latency_ms": tool_latency_ms,
            "token_usage": token_usage,
            "active_model": active_model,
            "notes_created_at": time.time() if is_notes else None,
        }

    elif intent == "specific_search":
        logger.info(f"Intent classified as 'specific_search'. Querying transcript with keyword: '{search_kw}'...")
        tool_start_t = time.time()
        search_res = mcp_client.execute_tool("search_transcript", video_id=video_id, query=search_kw, top_k=5)
        tool_latency_ms = round((time.time() - tool_start_t) * 1000, 1)
        chunks = search_res.get("results", [])
        is_relevant = search_res.get("relevant_match_found", True)

        if chunks and is_relevant:
            context_snippets = "\n\n".join(
                f"[{int(c.get('start_time', 0))//60:02d}:{int(c.get('start_time', 0))%60:02d}] (start: {int(c.get('start_time', 0))}s) {c.get('text', '')}"
                for c in chunks
            )

            sys_explain = SPECIFIC_TOPIC_EXPLAIN_PROMPT.format(
                video_id=video_id,
                user_request=user_request,
                context_snippets=context_snippets
            )

            explanation = None
            token_usage = {}
            active_model = "compound-beta-mini"
            llm_start_t = time.time()
            if llm is not None:
                try:
                    resp = llm.invoke([SystemMessage(content=sys_explain), HumanMessage(content=user_request)])
                    explanation = clean_think_tags(resp.content if isinstance(resp.content, str) else str(resp.content))
                    meta = getattr(resp, "response_metadata", {}) or {}
                    token_usage = meta.get("token_usage", {})
                    active_model = meta.get("model_name") or getattr(llm, "model_name", "compound-beta-mini")
                except Exception as ex:
                    logger.warning(f"LLM specific explanation failed: {ex}. Retrying with compound-beta-mini...")
                    try:
                        from langchain_groq import ChatGroq
                        fallback_llm = ChatGroq(model="compound-beta-mini", groq_api_key=settings.GROQ_API_KEY, temperature=0.2, max_tokens=1500)
                        resp = fallback_llm.invoke([SystemMessage(content=sys_explain), HumanMessage(content=user_request)])
                        explanation = clean_think_tags(resp.content if isinstance(resp.content, str) else str(resp.content))
                        meta = getattr(resp, "response_metadata", {}) or {}
                        token_usage = meta.get("token_usage", {})
                        active_model = "compound-beta-mini"
                    except Exception as ex2:
                        logger.warning(f"Fallback LLM also failed: {ex2}")
            llm_duration_ms = round((time.time() - llm_start_t) * 1000, 1)

            if not explanation:
                top = chunks[0]
                start_sec = int(top.get("start_time", 0))
                minutes = start_sec // 60
                seconds = start_sec % 60
                yt_link = f"https://www.youtube.com/watch?v={video_id}&t={start_sec}"
                explanation = f"Based on the video transcript, this topic is discussed around **[{minutes:02d}:{seconds:02d}]({yt_link})**.\n\n{top.get('text', '')}"

            out_guard = check_output_guardrails(explanation)
            sanitized_response = out_guard["cleaned_text"]
            eval_scorecard = evaluate_llm_interaction(
                user_request=user_request,
                actual_output=sanitized_response,
                retrieval_context=context_snippets,
                system_prompt=sys_explain,
                use_llm_judge=True
            )

            return {
                "messages": [AIMessage(content=sanitized_response)],
                "retrieved_chunks": chunks,
                "final_response": sanitized_response,
                "prompt_sent": sys_explain,
                "intent": "specific_search",
                "search_query": search_kw,
                "executed_tools": [
                    {"name": "search_transcript", "args": {"video_id": video_id, "query": search_kw, "top_k": 5}}
                ],
                "guardrail_status": {"input": guard_meta, "output": out_guard},
                "eval_scorecard": eval_scorecard,
                "is_blocked": False,
                "llm_latency_ms": llm_duration_ms,
                "intent_latency_ms": intent_latency_ms,
                "tool_latency_ms": tool_latency_ms,
                "token_usage": token_usage,
                "active_model": active_model,
            }
        else:
            # No relevant match found in transcript — explicitly transition to out_of_video.
            intent = "out_of_video"
            logger.info(
                f"No relevant transcript match for '{search_kw}' in video '{video_id}' "
                f"(chunks={len(chunks)}, relevant={is_relevant}). "
                f"Transitioning to out_of_video general knowledge path."
            )

    # Explicit out_of_video handling — reached either via LLM intent classification
    # or by falling through from specific_search when no relevant chunks were found.
    if intent == "out_of_video":
        logger.info(f"Topic '{user_request}' is not discussed in video '{video_id}'. Answering from general knowledge...")
        
        # Execute answer_from_general_knowledge MCP tool
        gk_tool_start = time.time()
        gk_tool_res = mcp_client.execute_tool(
            "answer_from_general_knowledge",
            query=user_request,
            reason=f"Topic '{user_request}' is not covered in video lecture '{video_id}'."
        )
        gk_tool_latency = round((time.time() - gk_tool_start) * 1000, 1)

        gk_sys = GENERAL_KNOWLEDGE_PROMPT.format(user_request=user_request)
        gk_answer = None
        token_usage = {}
        active_model = "compound-beta-mini"
        llm_start_t = time.time()
        if llm is not None:
            try:
                resp = llm.invoke([SystemMessage(content=gk_sys), HumanMessage(content=user_request)])
                gk_answer = clean_think_tags(resp.content if isinstance(resp.content, str) else str(resp.content))
                meta = getattr(resp, "response_metadata", {}) or {}
                token_usage = meta.get("token_usage", {})
                active_model = meta.get("model_name") or getattr(llm, "model_name", "compound-beta-mini")
            except Exception as ex:
                logger.warning(f"LLM general knowledge answer failed: {ex}. Retrying with compound-beta-mini...")
                try:
                    from langchain_groq import ChatGroq
                    fallback_llm = ChatGroq(model="compound-beta-mini", groq_api_key=settings.GROQ_API_KEY, temperature=0.2, max_tokens=1500)
                    resp = fallback_llm.invoke([SystemMessage(content=gk_sys), HumanMessage(content=user_request)])
                    gk_answer = clean_think_tags(resp.content if isinstance(resp.content, str) else str(resp.content))
                    meta = getattr(resp, "response_metadata", {}) or {}
                    token_usage = meta.get("token_usage", {})
                    active_model = "compound-beta-mini"
                except Exception as ex2:
                    logger.warning(f"Fallback LLM also failed: {ex2}")
        llm_duration_ms = round((time.time() - llm_start_t) * 1000, 1)

        if not gk_answer:
            gk_answer = (
                f"> **💡 Note:** This topic is not covered in the loaded video lecture. However, based on general knowledge:\n\n"
                f"The topic '{user_request}' is not discussed in this video lecture."
            )

        executed_tools = [
            {"name": "answer_from_general_knowledge", "args": {"query": user_request, "reason": f"Topic '{user_request}' is not in video '{video_id}'"}}
        ]

        out_guard = check_output_guardrails(gk_answer)
        sanitized_response = out_guard["cleaned_text"]
        eval_scorecard = evaluate_llm_interaction(
            user_request=user_request,
            actual_output=sanitized_response,
            retrieval_context="",
            system_prompt=gk_sys,
            use_llm_judge=True
        )

        return {
            "messages": [AIMessage(content=sanitized_response)],
            "retrieved_chunks": [],
            "final_response": sanitized_response,
            "prompt_sent": gk_sys,
            "intent": "out_of_video",
            "search_query": user_request,
            "executed_tools": executed_tools,
            "guardrail_status": {"input": guard_meta, "output": out_guard},
            "eval_scorecard": eval_scorecard,
            "is_blocked": False,
            "llm_latency_ms": llm_duration_ms,
            "intent_latency_ms": intent_latency_ms,
            "tool_latency_ms": gk_tool_latency,
            "token_usage": token_usage,
            "active_model": active_model,
        }

    # Safety fallback: should never be reached under normal operation.
    logger.error(f"agent_node reached unexpected state: intent='{intent}', user_request='{user_request}'")
    fallback_msg = "I encountered an unexpected error processing your request. Please try again."
    return {
        "messages": [AIMessage(content=fallback_msg)],
        "retrieved_chunks": [],
        "final_response": fallback_msg,
    }


def tool_node(state: AgentState) -> Dict[str, Any]:
    """MCP Tool Execution Node: Executes tool calls produced by LLM.

    Design Note — Direct MCP Pattern:
    This agent uses the "Direct MCP" pattern where agent_node classifies intent
    and calls MCP tools inline via mcp_client.execute_tool(). Because of this,
    the LLM in agent_node is NOT bound with .bind_tools(), so it will never
    produce tool_calls on the AIMessage it returns.

    As a result, the should_continue → "tools" branch is currently inactive.
    This node is kept here to support a future migration to the standard
    "LLM-tool-call" pattern (where get_llm_with_tools() binds tools and the
    LLM autonomously selects tools via tool_calls). In that pattern this node
    would intercept and execute those calls, then return ToolMessages back into
    the agent loop.
    """
    messages = state.get("messages", [])
    last_msg = messages[-1] if messages else None

    if not last_msg or not hasattr(last_msg, "tool_calls") or not last_msg.tool_calls:
        return {}

    tool_messages = []
    retrieved_chunks = list(state.get("retrieved_chunks", []))

    for tool_call in last_msg.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call.get("args", {})
        tool_id = tool_call.get("id", tool_name)

        logger.info(f"Executing tool call '{tool_name}' with args: {tool_args}")
        tool_result = mcp_client.execute_tool(tool_name, **tool_args)

        if tool_name == "search_transcript" and tool_result.get("success"):
            if tool_result.get("relevant_match_found"):
                retrieved_chunks.extend(tool_result.get("results", []))
        elif tool_name == "generate_video_notes" and tool_result.get("success"):
            retrieved_chunks.extend(tool_result.get("chunks", []))

        content_str = json.dumps(tool_result, ensure_ascii=False)
        tool_messages.append(ToolMessage(content=content_str, tool_call_id=tool_id))

    return {
        "messages": tool_messages,
        "retrieved_chunks": retrieved_chunks,
    }


def should_continue(state: AgentState) -> str:
    """Conditional Edge: Decides whether to execute a tool, trigger HITL interrupt, or finish."""
    messages = state.get("messages", [])
    last_msg = messages[-1] if messages else None

    if last_msg and hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "tools"

    if state.get("requires_human_approval") and state.get("notes"):
        return "human_approval"

    return "end"


def approve_notes_node(state: AgentState) -> Dict[str, Any]:
    """Human-in-the-Loop: Finalizes draft notes upon human approval."""
    notes = clean_think_tags(state.get("notes", ""))
    logger.info("Human approved draft notes.")
    return {
        "requires_human_approval": False,
        "final_response": notes,
        "messages": [AIMessage(content=f"Notes Approved!\n\n{notes}")],
    }


def revise_notes_node(state: AgentState) -> Dict[str, Any]:
    """Human-in-the-Loop: Revises draft notes based on explicit human feedback."""
    draft_notes = state.get("notes") or state.get("final_response") or ""
    human_feedback = state.get("human_feedback", "")
    video_id = state.get("video_id", "")
    logger.info(f"Revising notes based on human feedback: '{human_feedback}'")

    if not draft_notes or len(draft_notes.strip()) < 50:
        res = mcp_client.execute_tool("generate_video_notes", video_id=video_id)
        chunks = res.get("chunks", [])
        draft_notes = "\n\n".join(
            f"[{int(c.get('start_time', 0))//60:02d}:{int(c.get('start_time', 0))%60:02d}] {c.get('text', '')}"
            for c in chunks
        )

    llm = get_llm()
    token_usage = {}
    active_model = "compound-beta-mini"
    llm_duration_ms = 0.0
    if llm is not None:
        t0 = time.time()
        try:
            prompt_content = NOTES_REVISION_PROMPT.format(draft_notes=draft_notes, human_feedback=human_feedback)
            response = llm.invoke([
                SystemMessage(content="You are an expert AI educational assistant specialized in revising study notes based on user instructions."),
                HumanMessage(content=prompt_content),
            ])
            llm_duration_ms = round((time.time() - t0) * 1000, 1)
            revised_notes = clean_think_tags(
                response.content
                if isinstance(response.content, str)
                else "\n".join(x.get("text", "") for x in response.content if isinstance(x, dict))
            ).strip()
            meta = getattr(response, "response_metadata", {}) or {}
            token_usage = meta.get("token_usage", {})
            active_model = meta.get("model_name") or getattr(llm, "model_name", "compound-beta-mini")
        except Exception as e:
            logger.warning(f"LLM notes revision failed: {e}. Retrying with compound-beta-mini...")
            try:
                from langchain_groq import ChatGroq
                fallback_llm = ChatGroq(model="compound-beta-mini", groq_api_key=settings.GROQ_API_KEY, temperature=0.2, max_tokens=1500)
                prompt_content = NOTES_REVISION_PROMPT.format(draft_notes=draft_notes, human_feedback=human_feedback)
                response = fallback_llm.invoke([
                    SystemMessage(content="You are an expert AI educational assistant specialized in revising study notes based on user instructions."),
                    HumanMessage(content=prompt_content),
                ])
                llm_duration_ms = round((time.time() - t0) * 1000, 1)
                revised_notes = clean_think_tags(
                    response.content
                    if isinstance(response.content, str)
                    else "\n".join(x.get("text", "") for x in response.content if isinstance(x, dict))
                ).strip()
                meta = getattr(response, "response_metadata", {}) or {}
                token_usage = meta.get("token_usage", {})
                active_model = "compound-beta-mini"
            except Exception as e2:
                logger.warning(f"Fallback LLM revision also failed: {e2}")
                # Rule-based fallback: if user asked to remove a section like Executive Summary
                fb_lower = human_feedback.lower()
                if "remove" in fb_lower and "executive summary" in fb_lower:
                    cleaned_lines = []
                    skip = False
                    for line in draft_notes.splitlines():
                        if "## Executive Summary" in line or "##  Executive Summary" in line:
                            skip = True
                            continue
                        elif skip and line.startswith("## "):
                            skip = False
                        if not skip:
                            cleaned_lines.append(line)
                    revised_notes = "\n".join(cleaned_lines)
                else:
                    revised_notes = f"{draft_notes}\n\n--- Revised Notes ---\n Incorporated Feedback: '{human_feedback}'"
    else:
        revised_notes = f"{draft_notes}\n\n--- Revised Notes ---\n Incorporated Feedback: '{human_feedback}'"

    # Output Guardrails & Evaluation for revised notes
    out_guard = check_output_guardrails(str(revised_notes))
    sanitized_notes = out_guard["cleaned_text"]
    revision_prompt = prompt_content if 'prompt_content' in locals() else f"Revision Request: '{human_feedback}'"
    eval_scorecard = evaluate_llm_interaction(
        user_request=human_feedback,
        actual_output=sanitized_notes,
        retrieval_context=draft_notes,
        system_prompt=revision_prompt,
        use_llm_judge=True
    )

    return {
        "notes": sanitized_notes,
        "requires_human_approval": True,
        "final_response": sanitized_notes,
        "prompt_sent": revision_prompt,
        "token_usage": token_usage,
        "active_model": active_model,
        "llm_latency_ms": llm_duration_ms,
        "notes_created_at": time.time(),
        "guardrail_status": {"output": out_guard},
        "eval_scorecard": eval_scorecard,
        "is_blocked": False,
        "messages": [AIMessage(content=f" Notes Revised Based on Feedback:\n\n{sanitized_notes}")],
    }
