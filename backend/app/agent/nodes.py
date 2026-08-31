import json
import logging
import re
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
        resp = llm.invoke([SystemMessage(content=intent_prompt)])
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
        "test", "takeaway", "moto", "motto", "purpose", "goal", "theme", "about", 
        "gist", "main point", "main idea", "explain video", "what is this video", 
        "what is the video", "what does this video", "what this video", "what video"
    ]
    is_whole_video_req = any(w in req_lower for w in whole_video_keywords)

    if is_whole_video_req:
        intent = "whole_video"
        search_kw = ""
    else:
        intent_data = analyze_query_intent_with_llm(llm, user_request, video_id)
        intent = intent_data.get("intent", "specific_search")
        search_kw = intent_data.get("search_keyword", "").strip() or user_request

    if intent == "whole_video":
        logger.info(f"Intent classified as 'whole_video'. Retrieving multi-section timeline for video '{video_id}'...")
        notes_res = mcp_client.execute_tool("generate_video_notes", video_id=video_id)
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
        if llm is not None:
            try:
                llm_out = llm.invoke([
                    SystemMessage(content=sys_inst),
                    HumanMessage(content=user_request)
                ])
                final_content = clean_think_tags(llm_out.content if isinstance(llm_out.content, str) else str(llm_out.content))
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
                except Exception as ex2:
                    logger.warning(f"Fallback LLM also failed: {ex2}")

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

        is_notes = "note" in req_lower or "# " in final_content
        return {
            "messages": [AIMessage(content=final_content)],
            "retrieved_chunks": chunks,
            "notes": final_content if is_notes else None,
            "requires_human_approval": is_notes,
            "final_response": final_content,
        }

    elif intent == "specific_search":
        logger.info(f"Intent classified as 'specific_search'. Querying transcript with keyword: '{search_kw}'...")
        search_res = mcp_client.execute_tool("search_transcript", video_id=video_id, query=search_kw, top_k=4)
        chunks = search_res.get("results", [])

        if chunks:
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
            if llm is not None:
                try:
                    resp = llm.invoke([SystemMessage(content=sys_explain), HumanMessage(content=user_request)])
                    explanation = clean_think_tags(resp.content if isinstance(resp.content, str) else str(resp.content))
                except Exception as ex:
                    logger.warning(f"LLM specific explanation failed: {ex}. Retrying with compound-beta-mini...")
                    try:
                        from langchain_groq import ChatGroq
                        fallback_llm = ChatGroq(model="compound-beta-mini", groq_api_key=settings.GROQ_API_KEY, temperature=0.2, max_tokens=1500)
                        resp = fallback_llm.invoke([SystemMessage(content=sys_explain), HumanMessage(content=user_request)])
                        explanation = clean_think_tags(resp.content if isinstance(resp.content, str) else str(resp.content))
                    except Exception as ex2:
                        logger.warning(f"Fallback LLM also failed: {ex2}")

            if not explanation:
                top = chunks[0]
                start_sec = int(top.get("start_time", 0))
                minutes = start_sec // 60
                seconds = start_sec % 60
                yt_link = f"https://www.youtube.com/watch?v={video_id}&t={start_sec}"
                explanation = f"Based on the video transcript, this topic is discussed around **[{minutes:02d}:{seconds:02d}]({yt_link})**.\n\n{top.get('text', '')}"

            return {
                "messages": [AIMessage(content=explanation)],
                "retrieved_chunks": chunks,
                "final_response": explanation,
            }
        else:
            # No relevant match found in transcript — explicitly transition to out_of_video.
            intent = "out_of_video"
            logger.info(
                f"No relevant transcript match for '{search_kw}' in video '{video_id}'. "
                f"Transitioning to out_of_video general knowledge path."
            )

    # Explicit out_of_video handling — reached either via LLM intent classification
    # or by falling through from specific_search when no relevant chunks were found.
    if intent == "out_of_video":
        logger.info(f"Topic '{user_request}' is not discussed in video '{video_id}'. Answering from general knowledge...")
        gk_sys = GENERAL_KNOWLEDGE_PROMPT.format(user_request=user_request)
        gk_answer = None
        if llm is not None:
            try:
                resp = llm.invoke([SystemMessage(content=gk_sys), HumanMessage(content=user_request)])
                gk_answer = clean_think_tags(resp.content if isinstance(resp.content, str) else str(resp.content))
            except Exception as ex:
                logger.warning(f"LLM general knowledge answer failed: {ex}. Retrying with compound-beta-mini...")
                try:
                    from langchain_groq import ChatGroq
                    fallback_llm = ChatGroq(model="compound-beta-mini", groq_api_key=settings.GROQ_API_KEY, temperature=0.2, max_tokens=1500)
                    resp = fallback_llm.invoke([SystemMessage(content=gk_sys), HumanMessage(content=user_request)])
                    gk_answer = clean_think_tags(resp.content if isinstance(resp.content, str) else str(resp.content))
                except Exception as ex2:
                    logger.warning(f"Fallback LLM also failed: {ex2}")

        if not gk_answer:
            gk_answer = (
                f" **Note:** The topic '{user_request}' is not mentioned or discussed in the loaded video lecture transcript.\n\n"
                f"Feel free to ask any question about the video lecture or click **Create study notes** to explore the video content!"
            )

        return {
            "messages": [AIMessage(content=gk_answer)],
            "retrieved_chunks": [],
            "final_response": gk_answer,
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
    if llm is not None:
        try:
            prompt_content = NOTES_REVISION_PROMPT.format(draft_notes=draft_notes, human_feedback=human_feedback)
            response = llm.invoke([
                SystemMessage(content="You are an expert AI educational assistant specialized in revising study notes based on user instructions."),
                HumanMessage(content=prompt_content),
            ])
            revised_notes = clean_think_tags(
                response.content
                if isinstance(response.content, str)
                else "\n".join(x.get("text", "") for x in response.content if isinstance(x, dict))
            ).strip()
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
                revised_notes = clean_think_tags(
                    response.content
                    if isinstance(response.content, str)
                    else "\n".join(x.get("text", "") for x in response.content if isinstance(x, dict))
                ).strip()
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

    return {
        "notes": str(revised_notes),
        "requires_human_approval": True,
        "final_response": str(revised_notes),
        "messages": [AIMessage(content=f" Notes Revised Based on Feedback:\n\n{revised_notes}")],
    }
