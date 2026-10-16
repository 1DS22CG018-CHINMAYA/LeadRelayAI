"""Seed LeadRelay with realistic industrial packaging machinery leads.

Dates are computed relative to ``datetime.date.today()`` so the dashboard
always shows a meaningful mix of overdue, due-today and upcoming follow-ups.
"""

import datetime

from database import get_db_connection, init_db

# Each lead: name, company, phone, source, last_contact_offset (days ago),
# status, status_reason, follow_up_offset (days from today), draft, chats.
# Chats: list of (sender, message, timestamp).
LEADS = [
    # ---------------- OVERDUE (4) ----------------
    (
        "Mike Harrison", "Midwest Beverage Bottling", "+1-312-555-0147",
        "PackExpo 2026", 4, "HOT",
        "Requested a formal quote for two orbital stretch wrappers with "
        "480V 3-phase power and wants delivery before month-end.",
        -2,
        "Hi Mike, your quote for two 480V 3-phase orbital stretch wrappers "
        "is ready, and month-end delivery is still achievable. Can we "
        "review it on a 10-minute call today?",
        [
            ("BUYER", "Hi, we met at PackExpo. Need 2 orbital stretch "
             "wrappers for our bottling line. Can you quote?",
             "4 days ago at 10:12 AM"),
            ("REP", "Absolutely Mike. What power supply does your plant "
             "run on?", "4 days ago at 10:30 AM"),
            ("BUYER", "480V 3-phase. We need them shipped before "
             "month-end, budget is approved.", "4 days ago at 11:05 AM"),
        ],
    ),
    (
        "Priya Nair", "Apex Pharma Logistics", "+1-617-555-0182",
        "Website RFQ", 5, "HOT",
        "Submitted an RFQ for a heat shrink tunnel and asked for pricing "
        "and lead time to replace a failed unit.",
        -1,
        "Hi Priya, pricing for the heat shrink tunnel replacement is "
        "attached with a 3-week lead time. Shall I lock in a production "
        "slot for you today?",
        [
            ("BUYER", "Our old shrink tunnel failed. Need pricing and lead "
             "time on a replacement ASAP.", "5 days ago at 9:02 AM"),
            ("REP", "Sorry to hear that, Priya. What conveyor width and "
             "film type?", "5 days ago at 9:20 AM"),
            ("BUYER", "24-inch conveyor, POF film. Please send the price "
             "today if possible.", "5 days ago at 9:41 AM"),
        ],
    ),
    (
        "Tom Becker", "Great Lakes Confectionery", "+1-414-555-0119",
        "Distributor Referral", 9, "WARM",
        "Asked for the carton taper catalog and is reviewing specs with "
        "the plant engineer.",
        -2,
        "Hi Tom, did your plant engineer get a chance to review the "
        "carton taper specs? Happy to set up a quick call to answer any "
        "questions this week.",
        [
            ("BUYER", "Can you send your carton taper brochure? Our "
             "distributor recommended you.", "9 days ago at 2:15 PM"),
            ("REP", "Sent the catalog to your email, Tom. Any specific "
             "case sizes?", "9 days ago at 2:40 PM"),
            ("BUYER", "Thanks, I'll review with our plant engineer and get "
             "back.", "9 days ago at 4:05 PM"),
        ],
    ),
    (
        "Laura Chen", "Pacific Snack Co.", "+1-503-555-0163",
        "Cold Inbound", 21, "COLD",
        "Ghosted after two rep follow-ups on the band sealer proposal.",
        -1,
        "Hi Laura, checking in one last time on the continuous band sealer "
        "proposal. Should I keep it open for you, or close the file for "
        "now?",
        [
            ("REP", "Hi Laura, sharing the continuous band sealer proposal "
             "we discussed.", "3 weeks ago at 11:00 AM"),
            ("REP", "Following up on the proposal, any questions?",
             "2 weeks ago at 10:30 AM"),
        ],
    ),
    # ---------------- DUE TODAY (5) ----------------
    (
        "Carlos Ramirez", "Summit Food Packagers", "+1-720-555-0138",
        "PackExpo 2026", 2, "HOT",
        "Confirmed budget for a robotic palletizer and asked for final "
        "pricing to issue a PO this week.",
        0,
        "Hi Carlos, final pricing for the robotic palletizer is ready for "
        "your PO this week. Can I send the order form now?",
        [
            ("BUYER", "Budget approved for the robotic palletizer. Send "
             "final pricing, we want to issue a PO this week.",
             "2 days ago at 3:15 PM"),
            ("REP", "Great news Carlos! Finalizing pricing with "
             "installation included.", "2 days ago at 3:32 PM"),
        ],
    ),
    (
        "Jennifer Walsh", "Cascadia Logistics", "+1-206-555-0175",
        "Website RFQ", 3, "HOT",
        "Asked about 480V 3-phase specs for three high-speed carton tapers "
        "for a new distribution center.",
        0,
        "Hi Jennifer, confirming all three high-speed carton tapers run on "
        "480V 3-phase. Can we schedule a quote review call today?",
        [
            ("BUYER", "We're opening a new DC. Need 3 high-speed carton "
             "tapers. Do they support 480V 3-phase?",
             "3 days ago at 1:10 PM"),
            ("REP", "Yes, 480V 3-phase is standard. Throughput target?",
             "3 days ago at 1:25 PM"),
            ("BUYER", "About 30 cases/min. Please send a quote.",
             "3 days ago at 1:50 PM"),
        ],
    ),
    (
        "Raj Patel", "Heartland Dairy Co-op", "+1-515-555-0126",
        "Distributor Referral", 6, "WARM",
        "Evaluating stretch wrapper budget with engineering next month.",
        0,
        "Hi Raj, ahead of your engineering budget review next month, would "
        "an ROI sheet for the stretch wrapper help? I can send it today.",
        [
            ("BUYER", "Interested in a rotary ring stretch wrapper, but "
             "engineering reviews budget next month.",
             "6 days ago at 10:00 AM"),
            ("REP", "Understood Raj. I'll share specs so you're ready for "
             "that review.", "6 days ago at 10:22 AM"),
        ],
    ),
    (
        "Sarah O'Connell", "Northstar Pet Foods", "+1-612-555-0191",
        "PackExpo 2026", 7, "WARM",
        "Requested heat shrink tunnel brochure and is comparing specs.",
        0,
        "Hi Sarah, hope the heat shrink tunnel brochure was helpful. Would "
        "a short video demo help your comparison? Happy to share one today.",
        [
            ("BUYER", "Can you send the heat shrink tunnel brochure? "
             "Comparing a few vendors.", "7 days ago at 11:30 AM"),
            ("REP", "Sent! Let me know which specs matter most.",
             "7 days ago at 11:45 AM"),
        ],
    ),
    (
        "Dave Kowalski", "Rust Belt Hardware Supply", "+1-216-555-0154",
        "Cold Inbound", 30, "COLD",
        "Budget frozen until Q4 per last conversation.",
        0,
        "Hi Dave, a quick check-in as Q4 approaches. Want me to update the "
        "carton taper quote so it's ready when budget reopens?",
        [
            ("REP", "Hi Dave, any update on the carton taper quote?",
             "1 month ago at 9:15 AM"),
            ("BUYER", "Budget is frozen until Q4. Reach out then.",
             "1 month ago at 4:40 PM"),
        ],
    ),
    # ---------------- UPCOMING (11) ----------------
    (
        "Angela Brooks", "Bluegrass Distillers", "+1-502-555-0109",
        "Website RFQ", 1, "HOT",
        "Requested pricing on a case erector and carton taper line for "
        "shipment before month-end.",
        3,
        "Hi Angela, the case erector and carton taper line pricing is "
        "ready with month-end shipping. Can we confirm specs on a call "
        "Thursday?",
        [
            ("BUYER", "Need pricing on a case erector + carton taper line. "
             "Must ship before month-end.", "Yesterday at 3:15 PM"),
            ("REP", "On it Angela, sending pricing shortly.",
             "Yesterday at 3:40 PM"),
        ],
    ),
    (
        "Kevin Nguyen", "Golden State Produce", "+1-559-555-0144",
        "Distributor Referral", 4, "WARM",
        "Reviewing VFFS machine specs for a produce bagging line.",
        5,
        "Hi Kevin, any questions on the vertical form-fill-seal specs for "
        "your produce line? I can arrange a sample bag run this week.",
        [
            ("BUYER", "Looking at VFFS machines for bagging produce. Send "
             "specs please.", "4 days ago at 8:50 AM"),
            ("REP", "Specs sent, Kevin. We can also run your samples.",
             "4 days ago at 9:10 AM"),
        ],
    ),
    (
        "Michelle Torres", "Lone Star Meat Packers", "+1-210-555-0172",
        "PackExpo 2026", 8, "WARM",
        "Asked for continuous band sealer catalog after PackExpo booth "
        "visit.",
        7,
        "Hi Michelle, following up on the band sealer catalog from "
        "PackExpo. Would a 15-minute call help match a model to your "
        "line?",
        [],
    ),
    (
        "Brian Foster", "Evergreen Paper Goods", "+1-360-555-0133",
        "Cold Inbound", 10, "WARM",
        "Evaluating budget for an orbital stretch wrapper with engineering "
        "next month.",
        10,
        "Hi Brian, would a side-by-side spec sheet for the orbital stretch "
        "wrapper help your engineering review next month? I can send it "
        "today.",
        [],
    ),
    (
        "Nina Alvarez", "Sunbelt Nutraceuticals", "+1-480-555-0188",
        "Website RFQ", 5, "WARM",
        "Requested heat shrink tunnel catalog and is reviewing bundling "
        "specs.",
        6,
        "Hi Nina, did the heat shrink tunnel catalog cover your bundling "
        "needs? I can share a sizing recommendation if you send your "
        "pack dimensions.",
        [],
    ),
    (
        "Greg Thompson", "Atlantic Seafood Processors", "+1-207-555-0115",
        "Distributor Referral", 12, "WARM",
        "Reviewing robotic palletizer specs and evaluating floor space "
        "with engineering.",
        14,
        "Hi Greg, would a layout drawing of the robotic palletizer help "
        "your engineering team assess floor space? I can send one this "
        "week.",
        [],
    ),
    (
        "Hannah Lee", "Prairie Grain Millers", "+1-701-555-0129",
        "Cold Inbound", 3, "HOT",
        "Asked for a quote on a VFFS machine and 480V 3-phase "
        "compatibility for a new flour line.",
        4,
        "Hi Hannah, the VFFS quote for your flour line is ready and runs on "
        "480V 3-phase. Can we review it together on Friday?",
        [],
    ),
    (
        "Frank Mueller", "Keystone Building Products", "+1-717-555-0166",
        "PackExpo 2026", 45, "COLD",
        "Bought a stretch wrapper from a competitor last month.",
        21,
        "Hi Frank, hope the new wrapper is running well. If you need a "
        "carton taper or backup unit later, I'd be glad to help.",
        [
            ("REP", "Hi Frank, checking in on the stretch wrapper quote.",
             "6 weeks ago at 10:00 AM"),
            ("BUYER", "Thanks, but we went with another vendor on price.",
             "6 weeks ago at 2:30 PM"),
        ],
    ),
    (
        "Olivia Grant", "Coastal Cosmetics Fulfillment", "+1-305-555-0151",
        "Website RFQ", 28, "COLD",
        "Ghosted after two follow-ups on the carton taper quote.",
        18,
        "Hi Olivia, just checking if carton taping is still a priority "
        "for your team. Would you like an updated quote?",
        [],
    ),
    (
        "Steven Park", "Rocky Mountain Brewing", "+1-303-555-0197",
        "Distributor Referral", 35, "COLD",
        "Budget frozen until Q4 for the shrink tunnel project.",
        15,
        "Hi Steven, as Q4 planning begins, would you like a refreshed heat "
        "shrink tunnel quote for your budget review?",
        [],
    ),
    (
        "Diane Mitchell", "Gulf Coast Chemicals", "+1-713-555-0140",
        "Cold Inbound", 40, "COLD",
        "Chose a competitor's band sealer and has not responded since.",
        20,
        "Hi Diane, if your band sealing needs grow, we'd be glad to quote "
        "a backup unit. Would a quick spec sheet be useful?",
        [],
    ),
]


def _iso(offset_days: int) -> str:
    """ISO date ``offset_days`` from today (negative = past)."""
    return (datetime.date.today()
            + datetime.timedelta(days=offset_days)).isoformat()


def seed_data_if_empty() -> bool:
    """Seed the DB inside one transaction if empty. Returns True if seeded."""
    conn = get_db_connection()
    try:
        if conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0] > 0:
            return False
        with conn:  # atomic transaction: commits or rolls back
            for (name, company, phone, source, last_ago, status, reason,
                 follow_up, draft, chats) in LEADS:
                assert len(draft.split()) < 50, f"Draft too long: {name}"
                cur = conn.execute(
                    """INSERT INTO leads (name, company, phone, source,
                       last_contact_date, status, status_reason,
                       next_follow_up_date, draft_message, is_sent)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                    (name, company, phone, source, _iso(-last_ago), status,
                     reason, _iso(follow_up), draft),
                )
                conn.executemany(
                    """INSERT INTO chat_messages
                       (lead_id, sender, message, timestamp)
                       VALUES (?, ?, ?, ?)""",
                    [(cur.lastrowid, s, m, t) for s, m, t in chats],
                )
        return True
    finally:
        conn.close()


def print_summary() -> None:
    """Print a console summary of seeded leads by status and urgency."""
    today = datetime.date.today().isoformat()
    conn = get_db_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        msgs = conn.execute(
            "SELECT COUNT(*) FROM chat_messages").fetchone()[0]
        convs = conn.execute(
            "SELECT COUNT(DISTINCT lead_id) FROM chat_messages").fetchone()[0]
        by_status = dict(conn.execute(
            "SELECT status, COUNT(*) FROM leads GROUP BY status").fetchall())
        urgency = conn.execute(
            """SELECT
                 SUM(next_follow_up_date < ?),
                 SUM(next_follow_up_date = ?),
                 SUM(next_follow_up_date > ?)
               FROM leads""", (today, today, today)).fetchone()
    finally:
        conn.close()

    print("=" * 44)
    print(" LeadRelay Seed Summary  (today: %s)" % today)
    print("=" * 44)
    print(f" Total leads           : {total}")
    print(f" Total chat messages   : {msgs} ({convs} conversations)")
    print("-" * 44)
    for s in ("HOT", "WARM", "COLD"):
        print(f" {s:<22}: {by_status.get(s, 0)}")
    print("-" * 44)
    print(f" Overdue               : {urgency[0] or 0}")
    print(f" Due Today             : {urgency[1] or 0}")
    print(f" Upcoming              : {urgency[2] or 0}")
    print("=" * 44)


if __name__ == "__main__":
    init_db()
    seeded = seed_data_if_empty()
    print("Seeded fresh data." if seeded
          else "Leads already present; skipped seeding.")
    print_summary()
