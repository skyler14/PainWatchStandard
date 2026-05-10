from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from fastmcp import FastMCP


@dataclass
class QuestionnaireSession:
    session_id: str
    run_id: str
    device_id: str
    trigger_score: float
    activation_positive_count: int
    activation_window_count: int
    started_at_utc: str
    pain_scores: dict = field(default_factory=dict)
    sensor_summary: dict = field(default_factory=dict)
    testimony: list[str] = field(default_factory=list)
    certainty: dict[str, float] = field(default_factory=dict)
    status: str = "active"
    answers: dict[str, str | int | float | bool | None] = field(default_factory=dict)


QUESTIONNAIRE_ITEMS = [
    {
        "id": "what_happened",
        "label": "What happened around when the pain started?",
        "type": "open_text",
        "required": True,
    },
    {
        "id": "location",
        "label": "Where did you feel it most?",
        "type": "string",
    },
    {
        "id": "quality",
        "label": "What did it feel like?",
        "type": "multi_select",
        "options": ["sharp", "dull", "burning", "throbbing", "cramping", "other"],
    },
    {
        "id": "gpm_today_0_10",
        "label": "Pain today",
        "type": "integer",
        "min": 0,
        "max": 10,
    },
    {
        "id": "gpm_week_average_0_10",
        "label": "Average pain this week",
        "type": "integer",
        "min": 0,
        "max": 10,
    },
    {
        "id": "gpm_yes_no",
        "label": "GPM yes/no items",
        "type": "object",
        "fields": [
            "vigorous_activity",
            "moderate_activity",
            "carry_groceries",
            "stairs_many",
            "stairs_few",
            "walk_more_than_block",
            "walk_block_or_less",
            "bathing_or_dressing",
            "cut_down_activity_time",
            "accomplishing_less",
            "limited_activity_type",
            "extra_effort",
            "sleep_trouble",
            "religious_activity",
            "social_recreation",
            "travel_transportation",
            "fatigued",
            "relies_on_help",
            "never_completely_goes_away",
            "daily_pain",
            "several_times_weekly",
            "sad_or_depressed",
        ],
    },
]

FOLLOW_UPS = {
    "location": "Where did you feel it most?",
    "quality": "What did the pain feel like?",
    "activity_context": "What were you doing right before it changed?",
    "gpm_today_0_10": "On a zero to ten scale, how bad is it today?",
    "gpm_week_average_0_10": "On average this week, where has it been from zero to ten?",
    "sleep_trouble": "Has it been interfering with sleep?",
    "fatigued": "Has it been making you feel tired?",
    "relies_on_help": "Have you needed help from someone because of it?",
    "sad_or_depressed": "Has it been making you feel sad or down?",
}

sessions: dict[str, QuestionnaireSession] = {}


def register_tools(mcp: FastMCP) -> None:
    mcp.add_tool(start_questionnaire)
    mcp.add_tool(get_questionnaire)
    mcp.add_tool(submit_questionnaire_answers)
    mcp.add_tool(continue_dialogue)


def start_questionnaire(
    run_id: str,
    device_id: str,
    trigger_score: float,
    activation_positive_count: int = 7,
    activation_window_count: int = 10,
    pain_scores: dict | None = None,
    sensor_summary: dict | None = None,
) -> dict:
    """Start a questionnaire for a sustained pain activation event."""
    session = QuestionnaireSession(
        session_id=str(uuid4()),
        run_id=run_id,
        device_id=device_id,
        trigger_score=trigger_score,
        activation_positive_count=activation_positive_count,
        activation_window_count=activation_window_count,
        started_at_utc=datetime.now(timezone.utc).isoformat(),
        pain_scores=pain_scores or {},
        sensor_summary=sensor_summary or {},
    )
    session.certainty = _initial_certainty(session)
    sessions[session.session_id] = session
    return {
        "session": asdict(session),
        "items": QUESTIONNAIRE_ITEMS,
        "next_question": "What happened around when the pain started?",
        "missing_fields": _missing_fields(session),
        "revised_scores": _revised_scores(session),
    }


def get_questionnaire(session_id: str) -> dict | None:
    """Return questionnaire state and items."""
    session = sessions.get(session_id)
    if session is None:
        return None
    return {
        "session": asdict(session),
        "items": QUESTIONNAIRE_ITEMS,
        "next_question": _next_question(session),
        "missing_fields": _missing_fields(session),
        "revised_scores": _revised_scores(session),
    }


def submit_questionnaire_answers(session_id: str, answers: dict) -> dict | None:
    """Save answers and close the questionnaire session."""
    session = sessions.get(session_id)
    if session is None:
        return None
    session.answers.update(answers)
    if "what_happened" in answers:
        session.testimony.append(str(answers["what_happened"]))
    _update_certainty(session, answers)
    if not _missing_fields(session):
        session.status = "completed"
    return {
        "session": asdict(session),
        "next_question": _next_question(session),
        "missing_fields": _missing_fields(session),
        "revised_scores": _revised_scores(session),
    }


def continue_dialogue(session_id: str, response: str, answers: dict | None = None) -> dict | None:
    """Add conversational testimony and return the next highest-value question."""
    session = sessions.get(session_id)
    if session is None:
        return None
    session.testimony.append(response)
    merged_answers = answers or {}
    session.answers.update(merged_answers)
    _update_certainty(session, merged_answers)
    return {
        "session": asdict(session),
        "next_question": _next_question(session),
        "missing_fields": _missing_fields(session),
        "revised_scores": _revised_scores(session),
    }


def _initial_certainty(session: QuestionnaireSession) -> dict[str, float]:
    certainty = {item["id"]: 0.0 for item in QUESTIONNAIRE_ITEMS}
    if session.trigger_score >= 0.65:
        certainty["what_happened"] = 0.2
    return certainty


def _update_certainty(session: QuestionnaireSession, answers: dict) -> None:
    for field, value in answers.items():
        session.certainty[field] = 1.0 if value not in (None, "", []) else 0.0
    if session.testimony:
        text = " ".join(session.testimony).lower()
        keyword_fields = {
            "sleep": "sleep_trouble",
            "tired": "fatigued",
            "fatigue": "fatigued",
            "sad": "sad_or_depressed",
            "depressed": "sad_or_depressed",
            "stairs": "stairs_few",
            "walk": "walk_block_or_less",
            "help": "relies_on_help",
        }
        for keyword, field in keyword_fields.items():
            if keyword in text:
                session.certainty[field] = max(session.certainty.get(field, 0), 0.55)


def _missing_fields(session: QuestionnaireSession) -> list[str]:
    priority = [
        "what_happened",
        "location",
        "quality",
        "activity_context",
        "gpm_today_0_10",
        "gpm_week_average_0_10",
        "sleep_trouble",
        "fatigued",
        "relies_on_help",
        "sad_or_depressed",
    ]
    return [field for field in priority if session.certainty.get(field, 0) < 0.7]


def _next_question(session: QuestionnaireSession) -> str | None:
    missing = _missing_fields(session)
    if not missing:
        return None
    return FOLLOW_UPS.get(missing[0], "Can you say a little more about what changed?")


def _revised_scores(session: QuestionnaireSession) -> dict:
    yes_no = session.answers.get("gpm_yes_no", {})
    if not isinstance(yes_no, dict):
        yes_no = {}
    yes_count = sum(1 for value in yes_no.values() if value is True)
    today = _bounded_int(session.answers.get("gpm_today_0_10"))
    week = _bounded_int(session.answers.get("gpm_week_average_0_10"))
    total = yes_count + today + week
    adjusted = min(100, round(total * 2.38, 1))
    return {
        "gpm_total_0_42": total,
        "gpm_adjusted_0_100": adjusted,
        "gpm_band": "mild" if adjusted < 30 else "moderate" if adjusted <= 69 else "severe",
        "testimony_count": len(session.testimony),
        "certainty": session.certainty,
    }


def _bounded_int(value: object) -> int:
    try:
        return min(10, max(0, int(value)))
    except (TypeError, ValueError):
        return 0
