---
name: debugger
description: Find the root cause of errors, failed jobs, and wrong data in the Azure / Databricks migration. Use whenever a command, notebook, job, or test fails or gives unexpected results.
---

# Debugger

Find the real cause, fix it with the smallest change, and make sure the user
understands what went wrong. Every bug is a chance to learn how Databricks or
Azure works underneath.

## Process

1. **Capture** the exact error and where it happened (command, notebook cell,
   job run ID, task name).
2. **Reproduce small.** Use the small Bronze slice, local Spark, or a single
   task. Do not spend credit re-running a full job to test a guess.
3. **Find the cause.** Form a guess, check it with evidence (logs, a query, a
   `display()`), then move to the next guess if it is wrong.
4. **Fix** with the smallest change that addresses the cause, not the symptom.
5. **Verify** by re-running only what failed.
6. **Explain** in plain words: what broke, why, and how we would spot it faster
   next time. If it taught something about Databricks, add a line to
   `docs/databricks-notes.md`.

## Where to look

| Symptom | Look here |
|---|---|
| Job failed | Job run page: task output, then driver logs (stdout, stderr, log4j) |
| Slow job | Spark UI: stages with most time, skew, number of tasks / files read |
| Cluster died or never started | Cluster event log (termination reason, quota) |
| Python error with a long Java stack | Scroll to the first `Caused by` / Python frame; Py4J wraps the real error |
| Wrong numbers in Gold | Delta `DESCRIBE HISTORY`, compare versions with time travel |

## Common causes on this project

- **403 / `AuthorizationPermissionMismatch` on `abfss://`**: missing Storage
  Blob Data Contributor role, or missing Unity Catalog external location /
  storage credential.
- **`QuotaExceeded` when a cluster starts**: trial subscriptions have a low
  vCPU quota. Check with `az vm list-usage --location <region> -o table` and
  pick a smaller node type.
- **Schema mismatch on Delta write**: the incoming data changed. Decide on
  purpose whether to use `mergeSchema` for that one write; never turn on
  auto-merge globally.
- **`ConcurrentAppendException`**: two writers on the same Delta table; make
  the job run one at a time or narrow the `MERGE` condition.
- **Very slow reads**: too many small files. Run `OPTIMIZE` before blaming the
  cluster size.
- **Secret not found**: secret scope name or key mismatch, or the workspace
  identity lacks access to Key Vault.
