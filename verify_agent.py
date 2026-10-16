"""Automated integration verification for the LeadRelay agent.

Runs the full ``evaluate_lead_state`` pipeline (LangGraph -> Groq structured
output -> date clamping -> deterministic fallback) against synthetic,
in-memory leads. The production ``leads.db`` is never written to; the only
database access is a single read-only health check (SQLite ``mode=ro``).

Usage
-----
    python verify_agent.py              # use the engine configured in .env
    python verify_agent.py --offline    # force the deterministic fallback

Exit status is 0 when every check passes and 1 otherwise.
"""

from __future__ import annotations

import argparse
import datetime
import os
import sqlite3
import sys

from agent_graph import evaluate_lead_state, fallback_evaluate
from database import DB_PATH

EXPECTED_SEEDED_LEADS = 20
MAX_DRAFT_WORDS = 50
REQUIRED_KEYS = ("status", "status_reason", "next_follow_up_date",
                 "draft_message")

TODAY = datetime.date.today()
_results: list[tuple[str, bool, str]] = []


# --------------------------------------------------------------------------
# Synthetic data helpers
# --------------------------------------------------------------------------
def make_lead(name: str = "Alex Morgan") -> dict:
    """Return an in-memory lead dictionary (never persisted)."""
    return {"id": 0, "name": name, "company": "Test Packaging Co.",
            "phone": "+1-555-000-0000", "source": "Verification Suite",
            "last_contact_date": TODAY.isoformat()}


def msg(sender: str, text: str) -> dict:
    return {"sender": sender, "message": text, "timestamp": "Today at 9:00 AM"}


def days_out(iso_date: str) -> int:
    return (datetime.date.fromisoformat(iso_date) - TODAY).days


def record(name: str, passed: bool, detail: str = "") -> None:
    _results.append((name, passed, detail))
    tag = "[PASS]" if passed else "[FAIL]"
    print(f"{tag} {name}" + (f"  ({detail})" if detail else ""))


def check(name: str, fn) -> None:
    """Run one test; any assertion or unexpected error becomes a [FAIL]."""
    try:
        detail = fn() or ""
        record(name, True, detail)
    except AssertionError as exc:
        record(name, False, str(exc))
    except Exception as exc:  # noqa: BLE001
        record(name, False, f"{type(exc).__name__}: {exc}")


# --------------------------------------------------------------------------
# Test cases
# --------------------------------------------------------------------------
def test_hot() -> str:
    out = evaluate_lead_state(make_lead(), [
        msg("BUYER", "Can you quote the 480V orbital wrapper?")])
    assert out["status"] == "HOT", f"status was {out['status']}"
    assert out["next_follow_up_date"] == TODAY.isoformat(), (
        f"follow-up was {out['next_follow_up_date']}")
    return "HOT, follow-up today"


def test_warm() -> str:
    out = evaluate_lead_state(make_lead(), [
        msg("BUYER", "Please send the spec sheet for review next month.")])
    assert out["status"] == "WARM", f"status was {out['status']}"
    offset = days_out(out["next_follow_up_date"])
    assert 3 <= offset <= 5, f"follow-up was {offset} days out"
    return f"WARM, follow-up in {offset} days"


def test_cold() -> str:
    out = evaluate_lead_state(make_lead(), [
        msg("REP", "Hi Alex, sharing the wrapper proposal."),
        msg("BUYER", "We went with another vendor.")])
    assert out["status"] == "COLD", f"status was {out['status']}"
    offset = days_out(out["next_follow_up_date"])
    assert 14 <= offset <= 30, f"follow-up was {offset} days out"
    return f"COLD, follow-up in {offset} days"


def test_draft_constraints() -> str:
    scenarios = {
        "HOT": [msg("BUYER", "Can you quote the 480V orbital wrapper?")],
        "WARM": [msg("BUYER", "Please send the spec sheet for review "
                              "next month.")],
        "COLD": [msg("BUYER", "We went with another vendor.")],
        "GHOSTED": [msg("REP", "Sharing the band sealer proposal."),
                    msg("REP", "Following up on the proposal.")],
        "NEW": [],
    }
    for label, chat in scenarios.items():
        draft = evaluate_lead_state(make_lead(), chat)["draft_message"]
        words = len(draft.split())
        assert words < MAX_DRAFT_WORDS, (
            f"{label} draft has {words} words (limit {MAX_DRAFT_WORDS})")
        assert draft.count("?") == 1 and draft.rstrip().endswith("?"), (
            f"{label} draft must contain exactly one question ending "
            f"in '?': {draft!r}")
    return f"{len(scenarios)} drafts under {MAX_DRAFT_WORDS} words, one question each"


def test_bidirectional_rescoring() -> str:
    history = [msg("REP", "Hi Alex, sharing the wrapper proposal."),
               msg("BUYER", "We went with another vendor.")]
    before = evaluate_lead_state(make_lead(), history)
    assert before["status"] == "COLD", (
        f"precondition failed: expected COLD, got {before['status']}")
    history.append(msg("BUYER", "Plans changed. Please send an urgent quote "
                                "for the 480V orbital wrapper today."))
    after = evaluate_lead_state(make_lead(), history)
    assert after["status"] == "HOT", f"status stayed {after['status']}"
    assert after["next_follow_up_date"] == TODAY.isoformat()
    return "COLD -> HOT"


def test_fallback_schema() -> str:
    state = {**make_lead(), "lead_id": 0,
             "chat_history": [msg("BUYER", "Can you quote the 480V orbital "
                                           "wrapper?")],
             "status": "", "status_reason": "", "next_follow_up_date": "",
             "draft_message": ""}
    out = fallback_evaluate(state)
    for key in REQUIRED_KEYS:
        assert key in out, f"missing key {key!r}"
        assert isinstance(out[key], str) and out[key].strip(), (
            f"{key!r} must be a non-empty string")
    assert out["status"] in {"HOT", "WARM", "COLD"}
    datetime.date.fromisoformat(out["next_follow_up_date"])  # valid ISO date
    assert len(out["draft_message"].split()) < MAX_DRAFT_WORDS
    assert out["draft_message"].count("?") == 1
    return "all keys present and valid"


def test_db_health() -> str:
    assert os.path.exists(DB_PATH), f"{DB_PATH} not found"
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        count = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    finally:
        conn.close()
    assert count == EXPECTED_SEEDED_LEADS, (
        f"expected {EXPECTED_SEEDED_LEADS} leads, found {count}")
    return f"{count} leads, read-only"


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--offline", action="store_true",
                        help="ignore GROQ_API_KEY and test the fallback only")
    args = parser.parse_args()

    # agent_graph loads .env at import time; the key is checked per call,
    # so removing it here forces the deterministic engine.
    if args.offline:
        os.environ.pop("GROQ_API_KEY", None)
    engine = ("Groq LLM + deterministic fallback"
              if os.getenv("GROQ_API_KEY") else "deterministic fallback")

    print("=" * 60)
    print(" LeadRelay Agent Verification")
    print(f" Date: {TODAY.isoformat()}   Engine: {engine}")
    print("=" * 60)

    check("Test 1: HOT intent (quote request)", test_hot)
    check("Test 2: WARM intent (spec sheet request)", test_warm)
    check("Test 3: COLD intent (went with another vendor)", test_cold)
    check("Test 4: Draft under 50 words, exactly one question",
          test_draft_constraints)
    check("Test 5: Bidirectional re-scoring (COLD -> HOT)",
          test_bidirectional_rescoring)
    check("Test 6: Fallback schema conformity", test_fallback_schema)
    check("DB health: 20 seeded leads (read-only)", test_db_health)

    failed = [r for r in _results if not r[1]]
    print("-" * 60)
    print(f" {len(_results) - len(failed)}/{len(_results)} checks passed")
    print("=" * 60)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
