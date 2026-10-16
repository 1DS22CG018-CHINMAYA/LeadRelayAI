# FDE Take-Home Assignment

Build a working AI agent with a real screen a sales team can use. Submit within 36 hours of getting this doc.

## The problem

A small company sells packaging equipment to other businesses. It has 5 sales reps.

* Leads live in one Excel sheet and in WhatsApp chats with buyers.
* Reps forget to follow up, so good leads go cold.
* The owner can't see which leads are hot and who needs a reply today.

The owner wants one simple screen that tells each rep who to follow up with today, and what to say.

## What to build

Build a lead follow-up agent with a working web app on top. Vibe coding is expected: use any AI coding tool you like.

### Step 1. Make your own sample data

* At least 20 fake leads (name, company, phone, source, last contact date)
* At least 10 short WhatsApp-style chats between a rep and a buyer

### Step 2. The agent must:

1. Read the leads and the chats
2. Tag each lead as Hot, Warm or Cold, with a one-line reason
3. Set a next follow-up date for each lead
4. Draft the next follow-up message for each lead

### Step 3. The screen must:

* Show today's follow-ups at the top, most urgent first
* Make overdue follow-ups stand out clearly
* Let a rep open a lead and see the chat, the tag, the reason and the draft message
* Let a rep edit the draft and mark it as sent
* Let a rep add a new lead or a new chat, and have the agent update that lead

**Out of scope:** login, real WhatsApp sending, payments. Do not build these.

## What to submit

Reply to the assignment email within 48 hours with these 4 things:

| # | What | Details |
| --- | --- | --- |
| 1 | Live link | A deployed app we can open and use. No local setup. |
| 2 | Code | A GitHub repo we can see |
| 3 | Video | Max 3 minutes. Show the app working as a sales rep would use it. |
| 4 | Short note | Half a page: what you built, how the agent decides Hot/Warm/Cold, what AI tools you used, and what you would build next |

Missing any of the 4 means the submission is not reviewed.

## Rules

* Any language, framework, AI model or AI coding tool is fine.
* Free tiers are fine for hosting and AI models.
* Work alone. You must be able to explain every part of what you built.
* Stuck on something? Pick the simplest option, write it down in your note, and keep going.

## How we review it

We check each item as a pass or fail.

| Check | Pass means |
| --- | --- |
| It works | The live link opens and the main flow runs with no errors |
| Agent is useful | Hot/Warm/Cold tags and reasons make sense for the chats |
| Drafts are usable | A rep could send the draft message with small edits or none |
| Screen is clear | A rep knows who to call today within 10 seconds of opening it |
| Scope is right | Only what was asked, done well. No half-built extras. |
| You can explain it | Your note and video clearly explain how it works and why |

Pass 5 or more checks, and "It works" must be one of them, to move to the final round. In that round you walk us through your build life.