# Design: `ingest/flatten.py`

Status: approved 2026-10-21 (brainstorm session, Day 3).

## Understanding summary
- **What:** a local Python script that streams insurer in-network MRFs (`.zip` or `.json.gz`) and writes two Parquet tables per source file: `provider_group` and `negotiated_rate`.
- **Why:** Spark cannot split one 6 GB JSON document across workers. Flattening first lets Auto Loader / bronze ingest at scale.
- **For:** the Databricks bronze layer. Later it becomes a task in the monthly Databricks job (~Day 15).
- **Constraints:** stream with ijson, never unzip to disk, never `json.load` a whole file. Paths from CLI args / env vars. Test on small files first.
- **Non-goals:** type casts, fixes, DQ, NoVA filtering, exploding provider lists, upload to Azure, plan bridge. All of these happen in silver or other scripts.

## What the data is
Each insurer file is its contracted fee schedule: which provider group gets paid which rate for which service, in which network. Plans are not in the price files; the index maps plans to files (`plan_file_bridge`).

File layout (same for all 3 insurers, 31 fields verified 2026-10-21):
- Header: `reporting_entity_name`, `reporting_entity_type`, `last_updated_on`, `version`
- `provider_references[]`: provider_group_id -> network_name[], provider_groups[] (npi[], tin {type, value, business_name})
- `in_network[]`: billing code -> negotiated_rates[] -> provider_references[] (group ids) + negotiated_prices[]

## Assumptions
- Batches of ~50k rows keep memory flat on 6 GB files.
- Run time (rough, not measured): ~2 min per CareFirst part, ~40 min each for KP `-01` and Sentara HMO.
- Public data, no PHI, no secrets needed.
- Re-run on a finished file is skipped unless `--force`.

## Decision log
| # | Decision | Alternatives considered | Why |
|---|---|---|---|
| 1 | Insurers: KP, Sentara, CareFirst | Anthem, UHC, Oscar | CareFirst: small split files, no captcha, inner NoVA + FEHBP. Anthem index too big to filter; UHC huge, low NoVA share; Oscar individual-only. |
| 2 | Flatten = restructure only | + casts; + NoVA filter | Keeps the transformation work in Databricks; no NPI list yet for filtering. |
| 3 | One output folder per source file | One file per insurer-month; split by code type | Failure isolation, maps 1:1 to `files_ingested`, Parquet cannot append. |
| 4 | Provider IDs kept as a list column | Explode in Python | Avoids 1000x row blow-up on the laptop; explode is Spark's job (skew practice). |
| 5 | All values stored as text | Native JSON types | KP sends rates as strings, others as numbers; one type keeps bronze union clean. Silver casts to DECIMAL(18,2). |
| 6 | Test on CareFirst PPO + HMO parts first | All 3 at once | 2-minute feedback loop vs ~40 minutes. |
| 7 | All-or-nothing per file (`_tmp` then rename) | Partial + checkpoint; stop on first error | Never land half a file; ijson cannot resume mid-gz. |
| 8 | Files in scope: KP `-01`; Sentara HMO + OHIC; CareFirst PPO + BlueChoice HMO + FEHBP | All files | KP `-07` near-duplicate of `-01` (manifest size); skip national/MD-only/dental. |
| 9 | Two streaming passes + pyarrow fixed schema | One-pass event parser; load whole file | Simple and readable; extra read costs minutes. Fixed schema prevents Auto Loader schema drift. |

## Design

### Components
| Function | Job |
|---|---|
| `open_stream(path)` | Stream for `.zip` (the single JSON inside) or `.json.gz`. |
| `read_header(path)` | Header fields + insurer / month / filename date from path. |
| `iter_provider_groups(stream, meta)` | Pass 1: one row per provider group per TIN. Remote `location` refs: warn, count, skip. |
| `iter_rates(stream, meta)` | Pass 2: one row per billing code x rate block x price. |
| `BatchWriter(path, schema)` | Buffers rows, writes Parquet batches (~50k). |
| `flatten_file(path, out_root)` | `_tmp` -> pass 1 -> pass 2 -> rename. Deletes `_tmp` on error. Returns counts + seconds. |
| `main()` | Args: input files, `--out` (default env `FLATTEN_OUT_DIR`), `--limit N`, `--force`. One run-log line per file. |

### Data flow
```
data/<insurer>/<yyyy-mm>/<file>.zip|.json.gz
out/<insurer>/<yyyy-mm>/<source_file>/_tmp/                (during run)
out/<insurer>/<yyyy-mm>/<source_file>/provider_group.parquet
out/<insurer>/<yyyy-mm>/<source_file>/negotiated_rate.parquet
out/_runs/flatten_runs.jsonl
```
`insurer` and `file_month` come from the folder names. Input layout mirrors ADLS `landing/`.

### Output schema (all strings unless noted)
File columns on every row: `insurer, source_file, file_month, filename_date, header_last_updated, header_version`.

`provider_group`: file columns, `provider_group_id`, `network_name` list, `tin_type`, `tin_value`, `business_name`, `npi` list.

`negotiated_rate`: file columns, `billing_code_type`, `billing_code_type_version`, `billing_code`, `name`, `description`, `negotiation_arrangement`, `provider_group_ids` list, `negotiated_type`, `negotiated_rate`, `expiration_date`, `billing_class`, `setting`, `service_code` list, `billing_code_modifier` list, `bundled_codes` (JSON text or null).

Run log: `source_file, status (ok/failed/skipped), provider_group_rows, negotiated_rate_rows, in_network_items, remote_refs, empty_blocks, unknown_fields, seconds, error, run_at`.

Join key downstream: `source_file + provider_group_id` (id is unique only within a file).

### Error handling and edge cases
- File-level error: delete `_tmp`, log `failed`, continue with the next file.
- Final folder exists: `skipped` unless `--force` (then delete final, rename `_tmp`; Windows cannot rename over a folder).
- Stale `_tmp` from a crash: deleted at start.
- Zip with more than one JSON: fail with a clear message.
- Missing optional field: null. Unknown field: ignored, names listed once in the run log.
- Rate block with no prices / no provider ids: no row, counted.
- `0.00` rates and `9999-12-31` dates: kept as-is (silver flags them).
- ijson yields `Decimal`, so `str()` keeps rates exact; floats never involved.

### Testing
1. pytest on a tiny fixture (2 groups, 2 codes) as `.gz` and `.zip`: row counts, list columns, exact rate text, nulls, zip == gz, failed file leaves no folder, skip / force.
2. Real sample checks: CareFirst PPO `_10_of_35` -> `in_network_items = 609`; CPT 57452 -> `'146.77'` with group `690261199` (Chesapeake Urology). CareFirst HMO `hmo10` runs clean.
3. Schema check: CareFirst PPO, HMO and KP outputs have identical Parquet schemas.
4. Scale-up: KP `--limit 1000` -> full KP `-01` -> full Sentara HMO. Record real run times and peak memory in PROGRESS.md.

New dependencies: `pytest`, `duckdb`.

## Risks
- Sentara OHIC not inspected yet; assumed same layout.
- CareFirst schema 1.2.0 may have field differences in parts not scanned (only first 300 codes checked).
- Run-time estimates are rough; a full KP run may be slower on the laptop.
- Signed CareFirst URLs expire; download step (separate script) must always re-read the index.
