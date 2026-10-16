"""LeadRelay FastAPI backend.

Serves the single-page dashboard (``static/index.html``) and a JSON API over
SQLite. Lead tagging and draft generation are delegated to the LangGraph agent
in ``agent_graph.py`` (LangGraph + Groq ``llama-3.3-70b-versatile`` /
``openai/gpt-oss-120b`` with structured Pydantic output, backed by a
deterministic keyword fallback engine).

Endpoints
---------
GET    /api/health                  Liveness probe.
GET    /api/leads                   Leads sorted by urgency, then status.
POST   /api/leads                   Create a lead and evaluate it with the agent.
PATCH  /api/leads/{id}              Edit name/company/phone/source (no re-score).
POST   /api/leads/{id}/chat         Append a message and re-evaluate the lead.
PATCH  /api/leads/{id}/draft        Save a rep-edited draft.
PATCH  /api/leads/{id}/mark-sent    Mark follow-up sent and log it to the chat.
POST   /api/reset                   Drop and re-seed the demo database.
"""

from __future__ import annotations

import datetime
import os
import sqlite3
from contextlib import asynccontextmanager
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent_graph import evaluate_lead_state
from database import get_db_connection, init_db
from seed import seed_data_if_empty

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Create the schema and seed demo data on first start."""
    init_db()
    seed_data_if_empty()
    yield


app = FastAPI(title="LeadRelay API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------
class LeadCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    company: str = Field(min_length=1, max_length=160)
    phone: str = Field(min_length=5, max_length=32)
    source: str = Field(min_length=1, max_length=80)
    initial_notes: Optional[str] = Field(default=None, max_length=2000)


class ChatCreate(BaseModel):
    sender: Literal["REP", "BUYER"]
    message: str = Field(min_length=1, max_length=2000)


class DraftUpdate(BaseModel):
    draft_message: str = Field(min_length=1, max_length=1000)


class LeadUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    company: Optional[str] = Field(default=None, min_length=1, max_length=160)
    phone: Optional[str] = Field(default=None, min_length=5, max_length=32)
    source: Optional[str] = Field(default=None, min_length=1, max_length=80)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _today() -> str:
    return datetime.date.today().isoformat()


def _urgency(lead: dict, today: str) -> str:
    if lead["is_sent"]:
        return "SENT"
    if lead["next_follow_up_date"] < today:
        return "OVERDUE"
    if lead["next_follow_up_date"] == today:
        return "TODAY"
    return "UPCOMING"


def _fetch_chat(conn: sqlite3.Connection, lead_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, sender, message, timestamp FROM chat_messages "
        "WHERE lead_id = ? ORDER BY id", (lead_id,)).fetchall()
    return [dict(r) for r in rows]


def _serialize(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    lead = dict(row)
    lead["is_sent"] = bool(lead["is_sent"])
    lead["urgency"] = _urgency(lead, _today())
    lead["chat_messages"] = _fetch_chat(conn, lead["id"])
    return lead


def _get_lead_or_404(conn: sqlite3.Connection, lead_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM leads WHERE id = ?",
                       (lead_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return row


def _now_label() -> str:
    return datetime.datetime.now().strftime("Today at %I:%M %p").replace(
        " 0", " ")


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def index():
    path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(path):
        return FileResponse(path)
    return JSONResponse({"message": "LeadRelay API running. UI not built yet.",
                         "docs": "/docs"})


@app.get("/api/health")
def health() -> dict:
    return {"status": "healthy",
            "timestamp": datetime.datetime.now().isoformat()}


@app.get("/api/leads")
def list_leads() -> list[dict]:
    today = _today()
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """SELECT * FROM leads
               ORDER BY
                 CASE
                   WHEN is_sent = 0 AND next_follow_up_date < ? THEN 0
                   WHEN is_sent = 0 AND next_follow_up_date = ? THEN 1
                   WHEN is_sent = 0 THEN 2
                   ELSE 3
                 END,
                 CASE status WHEN 'HOT' THEN 0 WHEN 'WARM' THEN 1 ELSE 2 END,
                 next_follow_up_date ASC""",
            (today, today)).fetchall()
        return [_serialize(conn, r) for r in rows]
    finally:
        conn.close()


@app.post("/api/leads", status_code=201)
def create_lead(payload: LeadCreate) -> dict:
    today = _today()
    chat = []
    if payload.initial_notes and payload.initial_notes.strip():
        chat = [{"sender": "BUYER", "message": payload.initial_notes.strip(),
                 "timestamp": _now_label()}]
    lead_dict = payload.model_dump(exclude={"initial_notes"})
    lead_dict["last_contact_date"] = today
    evaluation = evaluate_lead_state(lead_dict, chat)

    conn = get_db_connection()
    try:
        with conn:
            cur = conn.execute(
                """INSERT INTO leads (name, company, phone, source,
                   last_contact_date, status, status_reason,
                   next_follow_up_date, draft_message, is_sent)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                (payload.name, payload.company, payload.phone,
                 payload.source, today, evaluation["status"],
                 evaluation["status_reason"],
                 evaluation["next_follow_up_date"],
                 evaluation["draft_message"]))
            lead_id = cur.lastrowid
            for m in chat:
                conn.execute(
                    "INSERT INTO chat_messages (lead_id, sender, message, "
                    "timestamp) VALUES (?, ?, ?, ?)",
                    (lead_id, m["sender"], m["message"], m["timestamp"]))
        return _serialize(conn, _get_lead_or_404(conn, lead_id))
    finally:
        conn.close()


@app.post("/api/leads/{lead_id}/chat")
def add_chat(lead_id: int, payload: ChatCreate) -> dict:
    conn = get_db_connection()
    try:
        lead = dict(_get_lead_or_404(conn, lead_id))
        with conn:
            conn.execute(
                "INSERT INTO chat_messages (lead_id, sender, message, "
                "timestamp) VALUES (?, ?, ?, ?)",
                (lead_id, payload.sender, payload.message.strip(),
                 _now_label()))
        history = _fetch_chat(conn, lead_id)
        evaluation = evaluate_lead_state(lead, history)
        with conn:
            conn.execute(
                """UPDATE leads SET status = ?, status_reason = ?,
                   next_follow_up_date = ?, draft_message = ?,
                   last_contact_date = ?, is_sent = 0
                   WHERE id = ?""",
                (evaluation["status"], evaluation["status_reason"],
                 evaluation["next_follow_up_date"],
                 evaluation["draft_message"], _today(), lead_id))
        return {"success": True,
                "updated_lead": _serialize(conn,
                                           _get_lead_or_404(conn, lead_id))}
    finally:
        conn.close()


@app.patch("/api/leads/{lead_id}/draft")
def update_draft(lead_id: int, payload: DraftUpdate) -> dict:
    conn = get_db_connection()
    try:
        _get_lead_or_404(conn, lead_id)
        with conn:
            conn.execute("UPDATE leads SET draft_message = ? WHERE id = ?",
                         (payload.draft_message.strip(), lead_id))
        return {"success": True,
                "updated_lead": _serialize(conn,
                                           _get_lead_or_404(conn, lead_id))}
    finally:
        conn.close()


@app.patch("/api/leads/{lead_id}")
def update_lead(lead_id: int, payload: LeadUpdate) -> dict:
    fields = {k: v.strip() for k, v in payload.model_dump().items()
              if v is not None and v.strip()}
    conn = get_db_connection()
    try:
        _get_lead_or_404(conn, lead_id)
        if fields:
            cols = ", ".join(f"{k} = ?" for k in fields)  # keys from schema
            with conn:
                conn.execute(f"UPDATE leads SET {cols} WHERE id = ?",
                             (*fields.values(), lead_id))
        return _serialize(conn, _get_lead_or_404(conn, lead_id))
    finally:
        conn.close()


@app.post("/api/reset")
def reset_demo() -> dict:
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("DROP TABLE IF EXISTS chat_messages;")
            conn.execute("DROP TABLE IF EXISTS leads;")
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500,
                            detail=f"Reset failed: {exc}") from exc
    finally:
        conn.close()
    init_db()
    seed_data_if_empty()
    return {"status": "ok", "message": "Demo data restored successfully"}


@app.patch("/api/leads/{lead_id}/mark-sent")
def mark_sent(lead_id: int) -> dict:
    conn = get_db_connection()
    try:
        lead = _get_lead_or_404(conn, lead_id)
        with conn:
            conn.execute("UPDATE leads SET is_sent = 1 WHERE id = ?",
                         (lead_id,))
            conn.execute(
                "INSERT INTO chat_messages (lead_id, sender, message, "
                "timestamp) VALUES (?, 'REP', ?, ?)",
                (lead_id, lead["draft_message"], _now_label()))
        return {"success": True,
                "updated_lead": _serialize(conn,
                                           _get_lead_or_404(conn, lead_id))}
    finally:
        conn.close()
