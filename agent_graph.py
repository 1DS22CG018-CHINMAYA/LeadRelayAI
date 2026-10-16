"""LeadRelay agent: a LangGraph ``StateGraph`` that tags leads and drafts
WhatsApp follow-ups.

Architecture
------------
1. The graph has a single ``evaluator`` node. It calls Groq
   (``llama-3.3-70b-versatile``, with ``openai/gpt-oss-120b`` as an automatic
   alternate if the first model is unavailable) and binds the reply to the
   ``AgentEvaluation`` Pydantic schema via structured output.
2. LLM output is passed through ``_sanitize``, which enforces the business
   rules below, so a model mistake can never produce an invalid result.
3. If ``GROQ_API_KEY`` is missing or the LLM call fails, a deterministic
   keyword-based engine (``fallback_evaluate``) runs instead. Callers always
   receive a valid evaluation.

Date-clamping business rules (``next_follow_up_date``, days from today)
----------------------------------------------------------------------
    HOT  = 0 days      (follow up today)
    WARM = 3-5 days
    COLD = 14-30 days

The most recent buyer message outweighs older ones, so a lead can move in
either direction (COLD -> HOT and HOT -> COLD) as the conversation evolves.
"""

from __future__ import annotations

import datetime
import logging
import os
import re
from typing import Literal, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

try:  # trust OS certificate store (fixes TLS behind AV/corporate proxies)
    import truststore

    truststore.inject_into_ssl()
except ImportError:  # pragma: no cover
    pass

load_dotenv()
logger = logging.getLogger("leadrelay.agent")

MODEL_NAME = "llama-3.3-70b-versatile"
# Tried in order (optional GROQ_MODEL override first); the first model the
# API key can access is cached in ``_active_model`` and reused.
MODEL_CANDIDATES = [m for m in dict.fromkeys([
    os.getenv("GROQ_MODEL", ""), MODEL_NAME, "openai/gpt-oss-120b",
]) if m]
_active_model: str | None = None
MAX_DRAFT_WORDS = 50


class AgentEvaluation(BaseModel):
    """Structured output schema the LLM must return (Pydantic-validated)."""

    status: Literal["HOT", "WARM", "COLD"]
    status_reason: str = Field(
        description="Exactly one concise sentence explaining the tag.")
    next_follow_up_date: str = Field(
        description="ISO date YYYY-MM-DD for the next follow-up.")
    draft_message: str = Field(
        description="WhatsApp follow-up under 50 words referencing the "
                    "buyer's machinery interest with exactly one question.")


class LeadAgentState(TypedDict):
    """State passed through the LangGraph evaluator node."""

    lead_id: int
    name: str
    company: str
    phone: str
    source: str
    last_contact_date: str
    chat_history: list[dict]
    status: str
    status_reason: str
    next_follow_up_date: str
    draft_message: str


SYSTEM_PROMPT = """You are LeadRelay, a sales follow-up assistant for a B2B \
company selling industrial packaging machinery (carton tapers/sealers, \
orbital and rotary ring stretch/pallet wrappers, heat shrink tunnels, \
vertical form-fill-seal machines, robotic palletizers, band sealers).

Today's date is {today}.

Classify the lead using ONLY the evidence in the conversation:
- HOT: buyer explicitly asked for pricing/quote, technical sizing \
(voltage, phase, dimensions, throughput), fast delivery, or has active \
budget allocation / PO intent. next_follow_up_date = {today}.
- WARM: buyer requested a brochure/catalog/specs, expressed interest, or is \
reviewing with engineering/procurement in 1-2 months. \
next_follow_up_date = 3 to 5 days after {today}.
- COLD: buyer stopped responding after multiple rep follow-ups, cited a \
budget freeze, or bought from a competitor. next_follow_up_date = 14 to 30 \
days after {today}.
The most recent buyer message outweighs older ones.

status_reason: exactly ONE concise sentence citing the concrete evidence.

draft_message rules:
- Under 50 words, warm professional B2B tone, address the buyer by first name.
- Reference their specific equipment interest.
- Contain exactly ONE question as the call-to-action \
(e.g. "Would 2 PM tomorrow work for a quick sizing call?").
- No placeholders, no emojis, no sign-off signature."""


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _today() -> datetime.date:
    """Current local date (single seam for date arithmetic)."""
    return datetime.date.today()


def _iso(offset: int) -> str:
    """ISO date ``offset`` days from today."""
    return (_today() + datetime.timedelta(days=offset)).isoformat()


def _first_name(name: str) -> str:
    """First token of a full name, or a neutral greeting if empty."""
    return (name or "there").split()[0]


def _format_chat(chat: list[dict]) -> str:
    """Render chat history as plain text for the LLM prompt."""
    if not chat:
        return "(no messages yet)"
    return "\n".join(
        f"[{m.get('timestamp', '')}] {m.get('sender', '?')}: "
        f"{m.get('message', '')}" for m in chat)


def _truncate_words(text: str, limit: int = MAX_DRAFT_WORDS - 1) -> str:
    """Hard-cap a draft below 50 words, ending on a question mark."""
    words = text.split()
    if len(words) <= limit:
        return text.strip()
    return " ".join(words[:limit]).rstrip(",;.") + "?"


# Keyword tables used by the deterministic fallback engine.
EQUIPMENT_KEYWORDS = [
    ("stretch wrapper", ["stretch wrap", "pallet wrap", "orbital",
                         "rotary ring", "wrapper"]),
    ("heat shrink tunnel", ["shrink tunnel", "heat shrink", "shrink"]),
    ("robotic palletizer", ["palletizer", "palletiser"]),
    ("vertical form-fill-seal machine", ["vffs", "form-fill-seal",
                                         "form fill seal", "bagging"]),
    ("band sealer", ["band sealer"]),
    ("carton taper", ["carton tap", "case tap", "carton seal", "taper",
                      "case erector"]),
]

HOT_KW = ["quote", "pricing", "price", "480v", "3-phase", "three phase",
          "voltage", "dimensions", "lead time", "asap", "urgent",
          "month-end", "month end", "budget approved", "budget is approved",
          "po ", "purchase order", "issue a po", "ship", "deliver"]
WARM_KW = ["brochure", "catalog", "catalogue", "spec", "interested",
           "review", "engineering", "procurement", "next month", "compare",
           "comparing", "demo"]
COLD_KW = ["frozen", "freeze", "another vendor", "competitor",
           "went with", "not interested", "no budget", "on hold",
           "next year", "q4", "pass for now"]


def detect_equipment(text: str) -> str:
    """Map free text to a machinery label for draft personalization."""
    low = text.lower()
    for label, keys in EQUIPMENT_KEYWORDS:
        if any(k in low for k in keys):
            return label
    return "packaging equipment"


# --------------------------------------------------------------------------
# Deterministic fallback
# --------------------------------------------------------------------------
def fallback_evaluate(state: LeadAgentState) -> dict:
    """Deterministic keyword classifier used when the LLM is unavailable.

    Applies the same HOT/WARM/COLD rules and follow-up windows as the LLM
    path (HOT = today, WARM = 3-5 days, COLD = 14-30 days) and always
    returns ``status``, ``status_reason``, ``next_follow_up_date`` and
    ``draft_message`` (under 50 words, one question).
    """
    chat = state.get("chat_history") or []
    all_text = " ".join(m.get("message", "") for m in chat)
    buyer_msgs = [m.get("message", "").lower() for m in chat
                  if m.get("sender") == "BUYER"]
    buyer_text = " ".join(buyer_msgs)
    last_buyer = buyer_msgs[-1] if buyer_msgs else ""
    equipment = detect_equipment(all_text)
    first = _first_name(state.get("name", ""))

    # Count trailing rep messages with no buyer reply (ghosting signal).
    trailing_rep = 0
    for m in reversed(chat):
        if m.get("sender") == "REP":
            trailing_rep += 1
        else:
            break

    def hit(keys: list[str], text: str) -> bool:
        return any(k in text for k in keys)

    if hit(COLD_KW, last_buyer) or (hit(COLD_KW, buyer_text)
                                    and not hit(HOT_KW, last_buyer)):
        status, follow = "COLD", _iso(21)
        if hit(["competitor", "another vendor", "went with"], buyer_text):
            reason = f"Buyer chose a competitor for the {equipment}."
            draft = (f"Hi {first}, hope the new setup is running well. If "
                     f"you need a backup {equipment} or spares later, "
                     f"could I keep you on our update list?")
        else:
            reason = f"Buyer cited a budget freeze on the {equipment} project."
            draft = (f"Hi {first}, checking in as budgets reopen. Would an "
                     f"updated {equipment} quote help your next planning "
                     f"cycle?")
    elif trailing_rep >= 2:
        status, follow = "COLD", _iso(14)
        reason = (f"Buyer has not replied after {trailing_rep} rep "
                  f"follow-ups on the {equipment}.")
        draft = (f"Hi {first}, one last check on the {equipment} proposal. "
                 f"Should I keep it open for you or close the file for now?")
    elif hit(HOT_KW, buyer_text):
        status, follow = "HOT", _iso(0)
        reason = (f"Buyer requested pricing or technical sizing for the "
                  f"{equipment}, showing active purchase intent.")
        draft = (f"Hi {first}, your {equipment} pricing and specs are ready. "
                 f"Would 2 PM tomorrow work for a quick call to finalize?")
    elif hit(WARM_KW, buyer_text) or buyer_msgs:
        status, follow = "WARM", _iso(4)
        reason = (f"Buyer is reviewing {equipment} information but has not "
                  f"requested a quote yet.")
        draft = (f"Hi {first}, hope the {equipment} details were useful. "
                 f"Would a 15-minute call this week help your team's "
                 f"review?")
    else:
        status, follow = "WARM", _iso(3)
        reason = (f"New {equipment} lead with no buyer response yet, so "
                  f"intent is still unconfirmed.")
        draft = (f"Hi {first}, thanks for your interest in our {equipment}. "
                 f"Could you share your line speed and product size so I "
                 f"can recommend the right model?")

    return {"status": status, "status_reason": reason,
            "next_follow_up_date": follow,
            "draft_message": _truncate_words(draft)}


# --------------------------------------------------------------------------
# LLM evaluation
# --------------------------------------------------------------------------
def _sanitize(result: AgentEvaluation) -> dict:
    """Clamp LLM output to the business rules.

    * Follow-up date must fall in the window for the status (HOT = 0 days,
      WARM = 3-5 days, COLD = 14-30 days); otherwise it is replaced with the
      window default (0 / 4 / 21 days).
    * ``status_reason`` is cut to its first sentence.
    * Typographic Unicode is normalized and the draft is capped below
      50 words.
    """
    try:
        date = datetime.date.fromisoformat(result.next_follow_up_date)
    except ValueError:
        date = None
    windows = {"HOT": (0, 0, 0), "WARM": (3, 5, 4), "COLD": (14, 30, 21)}
    lo, hi, default = windows[result.status]
    if date is None or not lo <= (date - _today()).days <= hi:
        date = _today() + datetime.timedelta(days=default)
    reason = re.split(r"(?<=[.!?])\s", _clean(result.status_reason))[0]
    return {"status": result.status, "status_reason": reason,
            "next_follow_up_date": date.isoformat(),
            "draft_message": _truncate_words(_clean(result.draft_message))}


_UNICODE_MAP = str.maketrans({
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-",
    "\u2014": "-", "\u2018": "'", "\u2019": "'", "\u201c": '"',
    "\u201d": '"', "\u2026": "...", "\u00a0": " ", "\u202f": " ",
})


def _clean(text: str) -> str:
    """Normalize typographic Unicode and collapse whitespace."""
    return " ".join(text.translate(_UNICODE_MAP).split())


def _llm_evaluate(state: LeadAgentState) -> dict:
    """Evaluate a lead with Groq structured output, then sanitize it."""
    from langchain_groq import ChatGroq  # imported lazily for fast fallback

    global _active_model
    user = (f"Lead: {state['name']} at {state['company']}\n"
            f"Source: {state['source']}\n"
            f"Last contact: {state['last_contact_date']}\n\n"
            f"WhatsApp conversation:\n{_format_chat(state['chat_history'])}")
    messages = [
        SystemMessage(content=SYSTEM_PROMPT.format(today=_today().isoformat())),
        HumanMessage(content=user),
    ]
    models = [_active_model] if _active_model else MODEL_CANDIDATES
    last_exc: Exception | None = None
    for model in models:
        llm = ChatGroq(model=model, temperature=0.2, timeout=20,
                       max_retries=1)
        try:
            result = llm.with_structured_output(AgentEvaluation).invoke(
                messages)
        except Exception as exc:  # noqa: BLE001
            if "model_not_found" in str(exc) or "decommissioned" in str(exc):
                last_exc = exc
                continue
            raise
        if not isinstance(result, AgentEvaluation):
            result = AgentEvaluation.model_validate(result)
        if _active_model != model:
            _active_model = model
            logger.info("Using Groq model: %s", model)
        return _sanitize(result)
    raise RuntimeError(f"No accessible Groq model: {last_exc}")


def evaluator_node(state: LeadAgentState) -> dict:
    """Graph node: LLM when a key is configured, else (or on error) fallback."""
    if os.getenv("GROQ_API_KEY"):
        try:
            return _llm_evaluate(state)
        except Exception as exc:  # noqa: BLE001 - never fail the request
            logger.warning("LLM evaluation failed, using fallback: %s", exc)
    return fallback_evaluate(state)


_builder = StateGraph(LeadAgentState)
_builder.add_node("evaluator", evaluator_node)
_builder.set_entry_point("evaluator")
_builder.add_edge("evaluator", END)
lead_graph = _builder.compile()


def evaluate_lead_state(lead_dict: dict, chat_history: list[dict]) -> dict:
    """Run the graph for one lead; returns status, reason, date and draft."""
    state: LeadAgentState = {
        "lead_id": int(lead_dict.get("id") or 0),
        "name": lead_dict.get("name", ""),
        "company": lead_dict.get("company", ""),
        "phone": lead_dict.get("phone", ""),
        "source": lead_dict.get("source", ""),
        "last_contact_date": lead_dict.get("last_contact_date")
        or _today().isoformat(),
        "chat_history": chat_history or [],
        "status": lead_dict.get("status", ""),
        "status_reason": lead_dict.get("status_reason", ""),
        "next_follow_up_date": lead_dict.get("next_follow_up_date", ""),
        "draft_message": lead_dict.get("draft_message", ""),
    }
    try:
        out = lead_graph.invoke(state)
        keys = ("status", "status_reason", "next_follow_up_date",
                "draft_message")
        return {k: out[k] for k in keys}
    except Exception as exc:  # noqa: BLE001
        logger.error("Graph invocation failed, using fallback: %s", exc)
        return fallback_evaluate(state)
