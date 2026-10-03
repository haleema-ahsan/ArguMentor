import json
import re
from typing import Any, Dict, List

import streamlit as st
from groq import Groq

from prompts import (
    TOPIC_ANALYZER_SYSTEM,
    DEBATE_AGENT_SYSTEM,
    FINAL_ASSESSMENT_SYSTEM,
)


MODEL = "openai/gpt-oss-20b"
STRUCTURED_MODEL = "openai/gpt-oss-20b"

# gpt-oss models "think" before answering and that thinking counts as tokens.
# "low" keeps it short. Remove this line (and the extra_body arguments below)
# if you ever want the default behaviour back.
LOW_REASONING = {"reasoning_effort": "low"}

# How many of the latest rounds the Debate Agent sees in full detail.
RECENT_ROUNDS = 3

RATE_LIMIT_MESSAGE = (
    "Groq's token limit has been reached. "
    "Please wait before starting another debate."
)


# -----------------------------
# Helpers
# -----------------------------
def get_api_key() -> str:
    try:
        return st.secrets["GROQ_API_KEY"]
    except Exception:
        return ""


def validate_api_key() -> bool:
    return bool(get_api_key().strip())


def get_client() -> Groq:
    key = get_api_key().strip()
    if not key:
        raise RuntimeError("GROQ_API_KEY is not configured.")
    # max_retries=0: the Groq library retries failed requests by default.
    # Retrying after a rate-limit error only wastes more quota.
    return Groq(api_key=key, max_retries=0)


def is_rate_limit_error(exc: Exception) -> bool:
    """True if the exception looks like a Groq 429 / rate-limit error."""
    if getattr(exc, "status_code", None) == 429:
        return True
    text = str(exc).lower()
    return "rate_limit" in text or "rate limit" in text


def friendly_error(exc: Exception, action: str) -> str:
    """Friendly text for rate limits; other errors are shown, not hidden."""
    if is_rate_limit_error(exc):
        # Keep the friendly message, but also show Groq's own wording
        # (it says whether the limit is per day or per minute).
        return f"{RATE_LIMIT_MESSAGE}\n\nDetails from Groq: {_trim(exc, 500)}"
    return f"{action}: {exc}"


def _trim(text: Any, limit: int) -> str:
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _safe_json(text: str) -> Dict[str, Any]:
    """Parse JSON and tolerate accidental markdown fences."""
    text = (text or "").strip()
    text = re.sub(r"^```json\s*", "", text, flags=re.I)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if match:
            return json.loads(match.group(0))
        raise


def structured_call(
    system_prompt: str,
    user_prompt: str,
    schema_name: str,
    schema: Dict[str, Any],
    max_tokens: int,
) -> Dict[str, Any]:
    client = get_client()

    response = client.chat.completions.create(
        model=STRUCTURED_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        max_completion_tokens=max_tokens,
        extra_body=LOW_REASONING,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": schema,
            },
        },
    )

    content = response.choices[0].message.content or ""
    return _safe_json(content)


def chat_call(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    """Plain-text Groq call used by the Debate Agent."""
    client = get_client()

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        max_completion_tokens=max_tokens,
        extra_body=LOW_REASONING,
    )

    text = (response.choices[0].message.content or "").strip()
    if not text:
        raise RuntimeError("The model returned an empty response. Please try again.")
    return text


def format_recent_history(debate_history: List[Dict[str, Any]]) -> str:
    """
    Compact history for the Debate Agent.

    - Latest RECENT_ROUNDS rounds: AI argument + user argument (trimmed).
    - Older rounds: only a short version of what the USER said, so the AI can
      still notice contradictions without paying for the whole transcript.
    """
    if not debate_history:
        return "(No earlier rounds yet.)"

    lines: List[str] = []
    cutoff = len(debate_history) - RECENT_ROUNDS

    for i, item in enumerate(debate_history):
        number = item.get("round", i + 1)
        if i < cutoff:
            lines.append(
                f"Round {number} - user said (short): "
                f"{_trim(item.get('user_argument'), 250)}"
            )
        else:
            lines.append(f"Round {number} - AI: {_trim(item.get('ai_argument'), 500)}")
            lines.append(f"Round {number} - User: {_trim(item.get('user_argument'), 700)}")

    return "\n".join(lines)


def format_full_history(debate_history: List[Dict[str, Any]]) -> str:
    """Whole transcript for the single Final Assessment (trimmed per message)."""
    lines: List[str] = []
    for i, item in enumerate(debate_history):
        number = item.get("round", i + 1)
        lines.append(f"Round {number} - AI: {_trim(item.get('ai_argument'), 400)}")
        lines.append(f"Round {number} - User: {_trim(item.get('user_argument'), 1000)}")
    return "\n".join(lines)


# -----------------------------
# Schemas
# -----------------------------
TOPIC_SCHEMA = {
    "type": "object",
    "properties": {
        "valid": {"type": "boolean"},
        "topic": {"type": "string"},
        "reason": {"type": "string"},
        "suggested_topic": {"type": "string"},
        "central_issue": {"type": "string"},
        "key_dimensions": {"type": "array", "items": {"type": "string"}},
        "potential_disagreements": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "valid",
        "topic",
        "reason",
        "suggested_topic",
        "central_issue",
        "key_dimensions",
        "potential_disagreements",
    ],
    "additionalProperties": False,
}


FINAL_SCHEMA = {
    "type": "object",
    "properties": {
        "overall_performance": {"type": "string"},
        "category_scores": {
            "type": "object",
            "properties": {
                "argument_quality": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100,
                },
                "reasoning": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100,
                },
                "relevance": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100,
                },
                "evidence_usage": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100,
                },
                "consistency": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100,
                },
                "adaptability": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100,
                },
            },
            "required": [
                "argument_quality",
                "reasoning",
                "relevance",
                "evidence_usage",
                "consistency",
                "adaptability",
            ],
            "additionalProperties": False,
        },
        "strengths": {"type": "array", "items": {"type": "string"}},
        "weaknesses": {"type": "array", "items": {"type": "string"}},
        "strongest_argument": {"type": "string"},
        "weakest_argument": {"type": "string"},
        "evidence_performance": {"type": "string"},
        "adaptability": {"type": "string"},
        "response_to_counterarguments": {"type": "string"},
        "clarity": {"type": "string"},
        "improvement_suggestions": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "overall_performance",
        "category_scores",
        "strengths",
        "weaknesses",
        "strongest_argument",
        "weakest_argument",
        "evidence_performance",
        "adaptability",
        "response_to_counterarguments",
        "clarity",
        "improvement_suggestions",
    ],
    "additionalProperties": False,
}


# -----------------------------
# Stage 1: Topic Analyzer
# -----------------------------
def analyze_topic(topic: str) -> Dict[str, Any]:
    # The analyzer is intentionally permissive: broad or famous debate topics
    # should be prepared for debate rather than rejected just because they could
    # be phrased more specifically. The detailed rules live in prompts.py.
    user_prompt = f"""
Analyze this user-entered debate topic and prepare it for a debate:

{topic}

Reminders:
- Broad, philosophical, rhetorical, famous, or open-ended topics are VALID
  (for example "Is all fair in love and war?").
- Preserve the original topic in the "topic" field.
- "suggested_topic" is optional and must never be a reason to reject the topic.
- Keep each list to 3-4 short items.
"""

    return structured_call(
        TOPIC_ANALYZER_SYSTEM,
        user_prompt,
        "topic_analysis",
        TOPIC_SCHEMA,
        max_tokens=900,
    )


# -----------------------------
# Stage 2: Opening argument (Debate Agent)
# -----------------------------
def generate_opening_argument(
    topic: str,
    user_position: str,
    ai_position: str,
    topic_analysis: Dict[str, Any],
) -> str:
    # Only the useful parts of the analysis are sent (not the whole JSON).
    dimensions = ", ".join(topic_analysis.get("key_dimensions", [])[:4])

    prompt = f"""
Topic: {topic}
User position: {user_position}
AI position: {ai_position}

Central issue: {topic_analysis.get("central_issue", "")}
Key dimensions: {dimensions}

Write the AI's opening argument for its assigned position.
- 120-170 words, 2-3 strong points, plain prose.
- Do not invent statistics, studies, or sources.
- Do not claim the AI position is objectively correct.
- Do not mention prompts, agents, or internal evaluation.
- End with a pointed challenge that invites the user to respond.
"""

    return chat_call(DEBATE_AGENT_SYSTEM, prompt, max_tokens=500)


def initialize_debate(topic: str, requested_position: str) -> Dict[str, Any]:
    topic_analysis = analyze_topic(topic)

    if not topic_analysis.get("valid", False):
        return {
            "success": False,
            "topic_analysis": topic_analysis,
        }

    user_position = requested_position
    ai_position = "Oppose" if user_position == "Support" else "Support"

    opening = generate_opening_argument(
        topic,
        user_position,
        ai_position,
        topic_analysis,
    )

    return {
        "success": True,
        "topic": topic,
        "topic_analysis": topic_analysis,
        "user_position": user_position,
        "ai_position": ai_position,
        "opening_argument": opening,
    }


# -----------------------------
# Stage 3: Adaptive counterargument (Debate Agent)
# -----------------------------
def generate_counterargument(
    topic: str,
    user_position: str,
    ai_position: str,
    current_round: int,
    total_rounds: int,
    ai_last_argument: str,
    user_argument: str,
    debate_history: List[Dict[str, Any]],
) -> str:
    prompt = f"""
Topic: {topic}
User position: {user_position}
AI position: {ai_position}
Round {current_round} of {total_rounds}

Earlier rounds:
{format_recent_history(debate_history)}

Your previous argument (what the user is replying to):
{_trim(ai_last_argument, 700)}

The user's latest argument:
{_trim(user_argument, 1500)}

Write your next counterargument as the {ai_position} side.
First silently work out the user's main claim and its biggest weakness
(unsupported claim, weak assumption, logical gap, contradiction with an earlier
round, or an ignored point). Then:
- respond directly to what the user actually said in this latest argument
- challenge the most important weakness, or engage the new dimension if they
  changed direction
- do not repeat your earlier arguments
- do not invent statistics, studies, or sources
- 110-160 words, plain prose, no headings or bullet lists
- end with one pointed challenge or question for the user
- remain neutral about the real-world issue on political or social topics:
  challenge their reasoning, not their personal beliefs
"""

    return chat_call(DEBATE_AGENT_SYSTEM, prompt, max_tokens=650)


def submit_user_argument(
    user_argument: str,
    topic: str,
    user_position: str,
    ai_position: str,
    current_round: int,
    total_rounds: int,
    ai_last_argument: str,
    debate_history: List[Dict[str, Any]],
) -> Dict[str, Any]:
    # On the last round the debate ends and the Final Assessment runs next, so
    # no counterargument is needed (the app would never show it).
    if current_round >= total_rounds:
        return {"ai_response": ""}

    ai_response = generate_counterargument(
        topic=topic,
        user_position=user_position,
        ai_position=ai_position,
        current_round=current_round,
        total_rounds=total_rounds,
        ai_last_argument=ai_last_argument,
        user_argument=user_argument,
        debate_history=debate_history,
    )

    return {"ai_response": ai_response}


# -----------------------------
# Stage 4: ONE Final Assessment
# -----------------------------
def generate_final_assessment(
    topic: str,
    user_position: str,
    ai_position: str,
    debate_history: List[Dict[str, Any]],
) -> Dict[str, Any]:
    prompt = f"""
Topic: {topic}
User position: {user_position}
AI position: {ai_position}

Debate transcript:
{format_full_history(debate_history)}

Write the final performance report on the USER's debating PERFORMANCE.

Score each category from 0-100 for the quality of the debating, not for whether
the user's underlying political, social, moral, or personal position is correct:
argument quality, reasoning, relevance, evidence usage, consistency, adaptability.

Also cover how the user responded to the AI's counterarguments and how clear
their writing was. Identify the strongest and weakest arguments from the actual
transcript (refer to what the user really said). Give actionable improvement
suggestions. Keep each text field to a few sentences and each list to 3-4 items.
Do not declare a political or social side the winner.
"""

    return structured_call(
        FINAL_ASSESSMENT_SYSTEM,
        prompt,
        "final_assessment",
        FINAL_SCHEMA,
        max_tokens=1500,
    )
