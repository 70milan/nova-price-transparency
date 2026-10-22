# NoVA Healthcare Price Transparency

Portfolio project: ingest real insurer + hospital price transparency data on Azure Databricks and build a Northern Virginia price-lookup app.
Question it answers: "What does an MRI / colonoscopy / delivery actually cost at each NoVA hospital, on my insurance?"

**Current status, findings and next step live in @docs/PROGRESS.md. Read it at the start of every session.**
Data source links: `docs/data_sources.md`.

## Working with JJ
- Senior Data Engineer (payer background: EDI 834/837, SQL Server/SSIS, ADF). Learning modern Databricks/lakehouse.
- Blunt, direct answers. ONE STEP AT A TIME: give the next step, wait for confirmation.
- Keep responses SHORT (answer + a few bullets + next step). End with "Want more detail?" when a topic was compressed.
- Ask clarifying questions only when genuinely needed.
- Uses voice-to-text; input can be garbled.
- Windows, PowerShell, Cursor. Venv at `.venv`. Always `python -m pip`, never bare `pip`.

## Session rules
- At the end of each session (or when JJ says "wrap up"): update `docs/PROGRESS.md`:
  move finished items to the day log, update "Next step", add new findings and DQ issues.
- Edit THIS file only when a standing rule, constraint, convention or architecture decision changes.
- Never commit anything under `data/` (raw MRFs are GBs; GitHub rejects >100 MB).

## Constraints
- $200 Azure free credit, 26-day plan, started 2026-10-19. Budget alert at $150.
- Free account (NOT upgraded). Databricks Premium trial, serverless compute only.
- Do NOT create the Databricks workspace before Day 5 (14-day trial clock starts on creation).

## Azure resources (East US, tags project=nova-pricing, env=dev, owner=jj)
- Resource group `rg-nova-pricing`
- Storage `stnovapricing70` (ADLS Gen2, HNS on, LRS). Containers: `landing`, `catalog`.
- Access connector `ac-nova-pricing` (system MI) has Storage Blob Data Contributor on the storage account. So does JJ's user.
- `az login`: tenant has security defaults, device-code flow is blocked. Use
  `az config set core.enable_broker_on_windows=false` then `az login --tenant <tenant-id>`.

## Architecture
sites → download+flatten job → ADLS `landing/<insurer>/<yyyy-mm>/` → Auto Loader → bronze → silver → gold
→ AI/BI dashboard + Genie, and Postgres B1MS → Streamlit/FastAPI on Container Apps (+ Azure Maps).
CI/CD: GitHub + Databricks Asset Bundles + GitHub Actions. `main` = prod, `dev` = daily work. Terraform only if time remains.

## Scope decisions
- Insurers: CareFirst BCBS (replaced Anthem 2026-10-21: small split files, no captcha, covers inner NoVA + FEHBP), Kaiser Permanente Mid-Atlantic, Sentara Health Plans.
- Anthem: deferred to "if time remains" (national index too large to filter cheaply).
- IN-NETWORK files only. Out-of-network skipped (sparse, 20-claim suppression); "if time remains", below Terraform.
- Hospitals: Inova (5), VHC Health, Sentara NoVA/Lake Ridge, Reston (HCA), StoneSprings (HCA).

## Conventions
- Large MRFs: stream with ijson straight from the zip/gz. Never unzip to disk, never `json.load` a whole file.
- Money: `DECIMAL(18,2)`, never float.
- Source values that don't match CMS standards: keep `<col>_raw` untouched, add `<col>_std`. Never overwrite raw.
- DQ pattern: allowed-value checks → known auto-fix rules → otherwise quarantine table. Log every load to `dq_results`.
- Keep every date a file carries (filename date, index last_updated, file header date).
- Flatten output: one folder per source file, `out/<insurer>/<yyyy-mm>/<source_file>/`. All values as text; casting happens in silver. All-or-nothing per file (`_tmp` then rename).

## Planned silver model
- `provider_group` (dim): provider_group_id, npi, tin_type, tin_value, business_name, insurer, file dates
- `negotiated_rate` (fact): insurer, billing_code_type_raw/_std, billing_code_type_version, billing_code, description,
  negotiation_arrangement, provider_group_id, negotiated_type, negotiated_rate DECIMAL(18,2), billing_class, setting, billing_code_modifier, service_code, bundled_codes,
  expiration_date, source_file, file dates. Grain: billing_code × provider_group_id × price. provider_group_id is unique only per file: join on source_file + provider_group_id.
- `plan_file_bridge`: plan_id, plan_id_type (hios/ein), plan_name, market_type, in_network_file

## Monthly automation (target)
read manifest/index → filter region → compare to `files_ingested` (name + size) → download new → flatten to Parquet
→ Auto Loader → bronze → silver → gold. One scheduled Databricks job, ~2nd of each month.

## 26-day plan
- Days 1–5: Azure setup, data sources, local flatten script (Days 3–4), table design, Postgres. Day 5: Databricks workspace + Unity Catalog.
- Days 6–9: land files, Auto Loader → bronze.
- Days 10–14: silver: flatten, NPI join, hospital standardization, DQ, SCD2, liquid clustering vs partitioning, skew/salting.
- Days 15–19: gold, insurer-vs-hospital mismatch report, scheduled job, CI/CD, dashboard, Genie. Trial ends ~Day 19.
- Days 20–24: November files as incremental load, export to Postgres, geocode, app.
- Days 25–26: README, architecture diagram, demo video, shut down compute.
- Cut first: Terraform → Genie → Medicare comparison → salting demo. Never cut: incremental load, DQ checks, mismatch report, README.