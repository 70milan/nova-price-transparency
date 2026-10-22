---
name: decide
description: Make one architecture or tooling choice quickly and record it as an ADR. Use when choosing between services or approaches (orchestration, IaC tool, streaming ingest, vector search, region, notebook compute, and so on).
---

# Decide

One decision at a time, fast. We have 30 days, so a decision should take one
conversation, not a week.

## Steps

1. **Name it** in one line, and why it comes up now.
2. **Give 2-3 options.** Include "skip it" or "keep it local" when that is
   honestly fine.
3. **For each option, four short lines:**
   - Cost this month (checked, not guessed; see `cost-check`)
   - What it teaches, especially about Databricks
   - How it breaks
   - How hard it is to undo
4. **Recommend one** and say why in two or three sentences.
   - If two options are close, pick the one that teaches more Databricks.
   - If still close, pick the one we can finish in a day.
5. **Stop and wait** for the user to agree or push back. Answer push-back
   directly. Do not start building until they agree.
6. **Write the ADR** once agreed: `docs/decisions/NNNN-<slug>.md`, next free
   number.

## ADR template

```markdown
# NNNN - <title>

Date: YYYY-MM-DD
Status: Accepted

## Context
What we need and why now. 3-5 lines.

## Options considered
- **A** - one line, cost, main downside
- **B** - one line, cost, main downside
- **C** - one line, cost, main downside

## Decision
What we picked and why.

## Cost impact
Expected $ this month and what bills by the hour, if anything.

## How to undo
Exact steps or commands.
```

Plain language throughout. No business jargon. Keep the whole answer on one
screen when possible.
