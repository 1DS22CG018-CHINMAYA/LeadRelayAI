# LeadRelay AI

**An AI follow-up copilot for B2B industrial packaging sales teams.**
LeadRelay reads every lead and WhatsApp conversation, decides who is Hot, Warm or Cold, schedules the next follow-up, and drafts the message, so each rep opens one screen and knows exactly who to contact today and what to say.

| | |
| --- | --- |
| **Live app** | `https://<your-service-name>.onrender.com` *(replace after deploying; see section 10)* |
| **Source code** | `https://github.com/<your-username>/<your-repo>` *(replace after pushing)* |
| **Stack** | Python 3.11, FastAPI, LangGraph, Groq (Llama 3.3 70B), SQLite, single-file HTML/JS UI |
| **Status** | Feature-complete; automated verification suite passing |

> **First-time visitors:** if the live app has been idle, the free hosting tier may take up to about a minute to wake up on the first request. Subsequent requests are fast.

---

## 1. The Problem

A small company sells packaging machinery (carton tapers, stretch wrappers, shrink tunnels, palletizers) to other businesses with a team of five reps.

| Pain point | Consequence |
| --- | --- |
| Leads are scattered across an Excel sheet and WhatsApp chats | No single source of truth |
| Reps forget to follow up | Good leads go cold |
| The owner cannot see lead temperature | No one knows who needs a reply **today** |

## 2. The Solution

LeadRelay turns unstructured chat history into a prioritized daily action list.

1. **Read** each lead and its full conversation.
2. **Tag** the lead HOT, WARM or COLD, with a one-sentence reason grounded in the chat.
3. **Schedule** the next follow-up date according to fixed business rules.
4. **Draft** a short, ready-to-send WhatsApp message.
5. **Re-score** automatically whenever a new message is added, in either direction (a COLD lead can become HOT, and the reverse).

The dashboard sorts by urgency (Overdue, then Due Today, then Upcoming, then Sent) and then by temperature, so a rep can see who to call within seconds of opening it.

## 3. Key Features

- **Urgency-first dashboard**: overdue follow-ups stand out; today's follow-ups sit at the top.
- **Lead detail view**: full chat, tag, reason, follow-up date and draft in one place.
- **Editable drafts**: reps can refine the message and mark it sent; the sent message is logged to the chat.
- **Add leads and chats**: every new lead or message triggers agent re-evaluation.
- **Seed data**: 20 realistic leads with WhatsApp-style conversations, with dates generated relative to today so the demo always shows a meaningful mix of overdue, due-today and upcoming items.
- **One-click demo reset**: restores the seeded dataset.
- **Resilient by design**: the app keeps working if the LLM is unavailable (see section 5).

> **Out of scope by design:** login, real WhatsApp sending and payments.

## 4. Requirements Coverage

Every item in the assignment brief maps to a concrete part of the system.

| Requirement | How it is met |
| --- | --- |
| At least 20 fake leads with name, company, phone, source, last contact date | `seed.py` creates **20 leads** with all five fields |
| At least 10 WhatsApp-style chats | Seeded conversations for the majority of leads (rep and buyer turns) |
| Agent reads leads and chats | `agent_graph.py` passes the lead profile and full chat history to the model |
| Hot / Warm / Cold tag with a one-line reason | Structured output; the reason is enforced to a single sentence |
| Next follow-up date | Set by the agent and clamped to fixed business windows |
| Drafted follow-up message | Under 50 words, one question, personalized to the equipment discussed |
| Today's follow-ups at the top, most urgent first | `GET /api/leads` orders Overdue, Due Today, Upcoming, Sent, then HOT, WARM, COLD |
| Overdue items stand out | Red highlighted rows, a pulsing indicator, "N days overdue" labels and a KPI counter |
| Open a lead to see chat, tag, reason and draft | Lead detail drawer |
| Edit the draft and mark it as sent | Editable draft box, with "Reset to AI Draft"; mark-sent logs the message to the chat |
| Add a new lead or chat; the agent updates the lead | `POST /api/leads` and `POST /api/leads/{id}/chat` re-run the agent and show the re-tag |
| **Out of scope:** login, real WhatsApp sending, payments | Deliberately **not built** |

## 5. Architecture

```
 Browser (static/index.html)
        │  JSON over HTTP
        ▼
 FastAPI  (main.py)  ──────────►  SQLite  (database.py, leads.db)
        │
        ▼
 LangGraph StateGraph  (agent_graph.py)
        │
        ├─ Groq LLM + structured Pydantic output
        │      llama-3.3-70b-versatile  (alternate: openai/gpt-oss-120b)
        │            │
        │            ▼
        │      _sanitize(): business-rule date clamping
        │
        └─ Deterministic keyword fallback  (fallback_evaluate)
               used when the key is missing or the LLM call fails
```

| File | Responsibility |
| --- | --- |
| `main.py` | FastAPI app, REST API, urgency sorting, static UI serving |
| `agent_graph.py` | LangGraph agent, Groq integration, sanitization, fallback engine |
| `database.py` | SQLite schema and connection helper (standard library only) |
| `seed.py` | Generates 20 leads and their conversations, relative to today |
| `static/index.html` | Single-page dashboard UI |
| `verify_agent.py` | Automated integration test suite |
| `render.yaml` | Render deployment blueprint |

## 6. How the Agent Decides

### Classification

| Status | Evidence in the conversation | Next follow-up |
| --- | --- | --- |
| **HOT** | Buyer asked for pricing or a quote, technical sizing (voltage, phase, dimensions, throughput), fast delivery, or has approved budget or PO intent | **Today (0 days)** |
| **WARM** | Buyer requested a brochure, catalog or specs, expressed interest, or is reviewing with engineering or procurement | **3 to 5 days** |
| **COLD** | Buyer went silent after multiple rep follow-ups, froze the budget, or chose a competitor | **14 to 30 days** |

The most recent buyer message outweighs older ones, which is what enables bidirectional re-scoring.

### Draft message rules

- Under **50 words**, professional and warm B2B tone, addressed to the buyer by first name.
- References the buyer's specific equipment interest.
- Contains **exactly one question** as the call to action.
- No placeholders, no emojis, no signature.

### Reliability: three layers

1. **Structured output.** The LLM must return the `AgentEvaluation` Pydantic schema (`status`, `status_reason`, `next_follow_up_date`, `draft_message`).
2. **Date clamping (`_sanitize`).** Even if the model returns an out-of-range date, it is replaced with the window default: HOT = 0 days, WARM = 3-5 days (default 4), COLD = 14-30 days (default 21). The reason is cut to one sentence and the draft is capped below 50 words.
3. **Deterministic fallback.** If `GROQ_API_KEY` is absent, or the Groq call errors or times out, a keyword-based engine applies the same rules and returns the same schema. The API never fails because of the model.

## 7. API Reference

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Liveness probe |
| GET | `/api/leads` | All leads, sorted by urgency, then status |
| POST | `/api/leads` | Create a lead and evaluate it with the agent |
| PATCH | `/api/leads/{id}` | Edit name, company, phone or source (no re-score) |
| POST | `/api/leads/{id}/chat` | Append a message and re-evaluate the lead |
| PATCH | `/api/leads/{id}/draft` | Save a rep-edited draft |
| PATCH | `/api/leads/{id}/mark-sent` | Mark the follow-up as sent and log it to the chat |
| POST | `/api/reset` | Restore the seeded demo data |

Interactive docs are available at `/docs` when the server is running.

## 8. Getting Started

**Requirements:** Python 3.11 or later and a free [Groq API key](https://console.groq.com/) (optional; the app runs without it using the fallback engine).

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure the environment (optional)
echo "GROQ_API_KEY=your_key_here" > .env

# 3. Run the app (the database is created and seeded on first start)
uvicorn main:app --reload
```

Open <http://localhost:8000>.

| Variable | Required | Description |
| --- | --- | --- |
| `GROQ_API_KEY` | No | Enables LLM evaluation. Without it, the deterministic fallback is used. |
| `GROQ_MODEL` | No | Overrides the preferred Groq model. |
| `LEADRELAY_DB` | No | Custom SQLite path. Defaults to `leads.db` beside the code. |

## 9. Verification

`verify_agent.py` is a standalone integration suite. It uses synthetic in-memory leads and never writes to `leads.db`; the only database access is a single read-only health check.

```bash
python verify_agent.py            # uses the engine configured in .env
python verify_agent.py --offline  # forces the deterministic fallback
```

| Check | Asserts |
| --- | --- |
| Test 1: HOT intent | Quote request is tagged HOT with a follow-up today |
| Test 2: WARM intent | Spec-sheet request is tagged WARM with a follow-up in 3-5 days |
| Test 3: COLD intent | "Went with another vendor" is tagged COLD with a follow-up in 14-30 days |
| Test 4: Draft constraints | Every draft is under 50 words and contains exactly one question |
| Test 5: Bidirectional re-scoring | A COLD history plus an urgent quote request flips to HOT |
| Test 6: Fallback schema | `fallback_evaluate()` returns all four keys with valid values |
| DB health | The seeded database holds 20 leads (read-only query) |

Each check prints `[PASS]` or `[FAIL]`, and the script exits with status `0` only if every check passes.

## 10. Deployment (Render)

The repository ships with a `render.yaml` blueprint, so deployment needs no manual configuration beyond one secret.

| Setting | Value |
| --- | --- |
| Service type | Web service, Python runtime |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Health check | `/api/health` |
| `PYTHON_VERSION` | `3.11` |
| `GROQ_API_KEY` | Secret, entered in the Render dashboard (`sync: false`) |

### Step by step

1. **Push to GitHub.** Make sure `.env` is not committed (it is already listed in `.gitignore`).
2. **Create the service.** In Render, choose **New > Blueprint**, connect the repository, and select it. Render reads `render.yaml`.
3. **Add the secret.** When prompted, paste your `GROQ_API_KEY`.
4. **Deploy.** Wait for the build to finish and the health check to turn green.
5. **Smoke test.** Open `https://<your-service-name>.onrender.com/api/health` and expect `{"status": "healthy", ...}`, then open the root URL to see the dashboard.
6. **Record the URLs.** Paste the live link and the repository link into the table at the top of this README.

### Checklist

- [ ] Dashboard loads and shows 20 leads with Overdue and Due Today counters
- [ ] Open a lead: chat, tag, reason and draft are visible
- [ ] Add a chat message: the agent re-tags the lead and the toast confirms it
- [ ] Edit a draft and mark it sent: it moves to the Sent tab and appears in the chat
- [ ] Add a new lead: it receives a tag, reason, date and draft

### Operational notes

- **Data persistence:** the free tier uses an ephemeral filesystem, so `leads.db` resets on each deploy or restart and the app re-seeds automatically on startup. This is intentional for a demo. For durable data, attach a persistent disk and point `LEADRELAY_DB` at it.
- **Demo reset:** the **Reset Demo Data** button in the header restores the seeded dataset, so a reviewer can always return to a clean state.
- **Cold starts:** free instances sleep when idle, so the first request after a pause is slower.
- **Without an API key:** the app still works end to end using the deterministic fallback engine, but tags and drafts come from keyword rules rather than the LLM.

## 11. Design Decisions

- **LangGraph over a bare LLM call:** a graph gives an explicit, extensible pipeline (more nodes, such as enrichment or escalation, can be added without restructuring).
- **Structured output plus clamping:** the LLM supplies judgment, while code enforces the invariants that must always hold.
- **Deterministic fallback:** the product remains usable offline or when the free-tier model is rate-limited, and the tests can run without network access.
- **SQLite and a single-file UI:** the simplest stack that satisfies the requirements, with no build step and no external services.

## 12. Roadmap

- Per-rep ownership and a manager view of the whole pipeline
- Real WhatsApp Business API integration for sending and receiving
- Spreadsheet import for existing lead lists
- Learned lead scoring from won and lost deals
- Persistent managed database for multi-instance deployments

---

*LeadRelay AI. Built with Python, FastAPI, LangGraph, Groq and SQLite.*
