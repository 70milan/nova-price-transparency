---
name: code-check
description: Final check before finishing code, IaC, or notebooks in the NoVA price transparency project, and before any git add, commit, or push. Covers secrets, hardcoded values, large/raw data files, .gitignore, Azure tags, repeatable writes, MRF data conventions, and the step-by-step git rules.
---

# Code check

Run through this before saying a piece of code is done, and before any git operation.
Report each item as pass / fail / not applicable. Fix fails before moving on.

## Checklist: code

- [ ] **No secrets in files.** Keys live in Key Vault or a Databricks secret
      scope. `.env.example` has names only, empty values. No SAS tokens or
      connection strings in code, notebooks, or docs.
- [ ] **Nothing hardcoded in code.** No storage account names, container names,
      paths, subscription IDs, tenant IDs, or usernames. Read them from env vars
      or config (`AZURE_STORAGE_ACCOUNT`, `AZURE_LANDING_CONTAINER`,
      `AZURE_CATALOG_CONTAINER`). Docs may name resources; code may not.
- [ ] **No personal info** in code, comments, or commit messages.
- [ ] **No emojis** in code, comments, logs, or docs.
- [ ] **Source project untouched.** Nothing written under `predection_project/`.

## Checklist: data conventions (this project)

- [ ] **Large MRFs are streamed.** ijson straight from the zip/gz. No unzipping
      to disk, no `json.load` / `json.loads` on a whole file, no `.read()` of
      the full stream.
- [ ] **Money is `DECIMAL(18,2)`** (or `decimal.Decimal` in Python). Never float.
      The cast handles both string (KP) and number (Sentara) inputs.
- [ ] **Raw values are kept.** Non-CMS values stay in `<col>_raw`; fixes go in
      `<col>_std`. Nothing overwrites raw.
- [ ] **Bad rows are kept, not dropped.** Quarantine table or `_rescued_data`.
      $0.00 rates and sentinel dates are flagged, not silently filtered.
- [ ] **Every load logs to `dq_results`** (once the table exists).
- [ ] **All file dates kept:** filename date, index `last_updated_on`, file
      header date.
- [ ] **Repeatable.** Running twice gives the same result: `MERGE` on keys,
      Auto Loader checkpoints, overwrite-by-partition, no blind appends.
      `files_ingested` (name + size) prevents re-downloading.
- [ ] **Tested on the small slice first** (first N `in_network` items or one
      small file) before a full 5-6 GB run.

## Checklist: Azure

- [ ] **Every Azure resource in IaC is tagged** `project=nova-pricing`,
      `env=dev`, `owner=jj`, region East US, in `rg-nova-pricing`.
- [ ] **Names follow the existing pattern:** `<type>-nova-pricing[-<purpose>]`
      (storage accounts: `stnovapricing<nn>`, no dashes).
- [ ] **Cost:** anything billable goes through the `cost-check` skill first.

## Git rules

`main` = prod, `dev` = daily work. Commit to `dev` unless told otherwise.
Git push only happens when the user explicitly says so.

1. **Check `.gitignore`** covers: `.env`, `.venv/`, `__pycache__/`, `*.pyc`,
   `data/`, raw source formats outside `data/` (`*.zip`, `*.gz`, `*.xlsx`,
   `*.parquet`), `*.tfstate*` and `.terraform/` (if Terraform),
   `.databricks/` (bundle state), scratch and debug output, `.idea/`,
   `.vscode/`, `.claude/settings.local.json`.
2. **Check staged size and paths.** Nothing under `data/`, no file over 50 MB
   (GitHub rejects 100 MB; warn well before). Run `git status` and
   `git diff --cached --stat` and show the result.
3. **Step A:** list the exact files to `git add`. Wait for approval.
4. **Step B:** propose the commit message. Wait for approval.
5. **Step C:** push only after the user says push.
