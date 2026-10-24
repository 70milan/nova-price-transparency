# Progress Log

## Next step
1. Design approved: `docs/design_flatten.md`. Move KP + Sentara zips to `data/kp/2026-10/` and `data/sentara/2026-10/`.
2. `ingest/flatten.py` skeleton written + smoke-tested (pass 1 OK: 23,953 provider_group rows on CareFirst PPO part 10). NEXT: JJ writes the `TODO(human)` loop in `iter_rates()` (rate blocks -> one row per price), then run pytest fixture + CareFirst checks. Test on CareFirst PPO `_10_of_35` + HMO `hmo10` parts first, then KP `-01`, then Sentara HMO.
3. Commit pending changes (via code-check): `.gitignore`, `hello.txt` deletion, `CLAUDE.md`, `.githooks/`, `.claude/skills/`, docs.
4. Before Day 5: brainstorm the gold star schema (conformed dims for the mismatch report).

## Open items
- KP: `-04` / `-07` skipped. Manifest sizes: `-01` 269,913,911 / `-07` 269,932,025 (likely near-duplicate) / `-04` 251,075,590. Confirm later in Databricks (hash + EXCEPT).
- KP: how many provider groups are NoVA hospitals? Needs NPI lookup.
- CareFirst replaced Anthem (2026-10-21). File scope approved: PPO + BlueChoice HMO (issuers GHMSI, BLUECHOICE) + FEHBP. Skip "National in-network" files, CareFirst of Maryland-only, dental (DHMO).
- CareFirst samples in `data/carefirst/2026-10/`: 3 indexes (hmo, ppo, FEHBP), PPO part `_10_of_35`, HMO part `hmo10`. 4 indexes not downloaded (cfa, ncas, netlease, par).
- Sentara: download OHIC zip (approved scope). Verify OHIC = PPO/POS side via index plan names.
- KP scope: `-01` only.
- Hospitals: UVA Prince William / Haymarket MRF not found. Reston/StoneSprings current HCA links need verifying.
- Nothing uploaded to Azure yet.

---

## Day log

### Day 3 — 2026-10-20 / 21
- Tooling: rewrote `code-check` skill for this project; added `brainstorm` skill; `.gitignore` fixed (CLAUDE.md now tracked, zip/gz/xlsx/.vscode/.databricks added); `hello.txt` deleted; git pre-commit hook `.githooks/pre-commit` (blocks data/, .env, zip/gz/xlsx/parquet, >50 MB), enabled with `git config core.hooksPath .githooks`.
- Replaced Anthem with CareFirst BCBS (direct URLs in page HTML, no captcha). Oscar/UHC rejected (individual-only / huge files, low NoVA share).
- Verified all 3 insurers share the same 31 JSON fields (scanned first 300 codes each). Only KP has `bundled_codes`.
- Brainstorm `flatten.py` decisions:
  1. Insurers: KP, Sentara, CareFirst.
  2. Flatten = restructure only; all casts/fixes/DQ/NoVA filter in silver.
  3. Output: one folder per source file `out/<insurer>/<yyyy-mm>/<source_file>/{provider_group,negotiated_rate}.parquet`.
  4. Provider IDs kept as a list column; silver explodes.
  5. All values as text (rates included); silver casts to DECIMAL(18,2).
  6. Test on CareFirst PPO + HMO parts first.
  7. All-or-nothing per file: write to `_tmp`, rename on success, else log + continue.
  8. Files in scope: KP `-01`; Sentara HMO + OHIC; CareFirst PPO + BlueChoice HMO + FEHBP.
  9. Approach A: two streaming passes (provider list, then prices) + pyarrow writer with fixed schema.

### Day 1 — 2026-10-19
- Budget alert ($150), resource group, storage account + containers, access connector, role assignments.
- GitHub repo `70milan/nova-price-transparency`, folders, venv, requirements, `main` + `dev` branches.
- `az login` working (security defaults block device code; fixed by disabling WAM broker + `--tenant`).
- Test upload to `landing/` with `--auth-mode login` succeeded.

### Day 2 — 2026-10-19
- Located MRFs for all 3 insurers and NoVA hospitals → `docs/data_sources.md`.
- KP: Mid-Atlantic file list wouldn't render (JS + ad blocker). Found KP's monthly manifest via browser DevTools Network tab.
- KP: read all 3 Mid-Atlantic indexes, downloaded core file, mapped JSON structure, confirmed real prices.
- Decided: in-network only for all insurers.
- Created `CLAUDE.md` (standing rules) and this file (moving state).
- Sentara HMO zip downloaded to `data/` and inspected (3 checks). Same layout as KP; 6 new DQ findings (#10–15).
- Moved venv into the repo (`nova-price-transparency/.venv`), rebuilt with identical package versions; old `azure_nova_pricing/.venv` deleted.

---

## Findings by source

### KP Mid-Atlantic
- Manifest: `https://healthy.kaiserpermanente.org/pricing/innetwork/YYYY-MM_List.txt` (lines: `path  size_bytes`). Mid-Atlantic = `/ma/`. Use for automated discovery.
- Indexes → files:
  - `KFHP-MA_index` → `-01`: Kaiser Foundation Health Plan HMO plans, ~300, VA/MD/DC, individual + group, HIOS ids. CORE FILE.
  - `KPIC-MA_index` → `-04`: Kaiser Permanente Insurance Company group products. 3 issuer-level HIOS ids.
  - `SF-MA_index` → `-07`: self-funded employer plans (Target, Accenture, General Dynamics, ...). plan_id_type = EIN.
- `-01`: 270 MB zipped, 5.72 GB unzipped, single JSON, in `data/`.
- Layout: header → `provider_references` (group id → NPIs + TIN + business_name) → `in_network`.
- Nesting: in_network → negotiated_rates[] → provider_references[] + negotiated_prices[]. Flatten = explode twice.
- HIOS prefix = state: `95185VA` Virginia, `94506DC` DC, `90296MD` Maryland.
- Example: MS-DRG 001 heart transplant, $1,042,518 at group 2390001 vs $400,000 at groups 4530001/5560001/6600001.

### Sentara
- Index: `https://mrfproddestinationdata.blob.core.windows.net/sentara-mrf-output/2026-10-01_Sentara-INN_index.json`
- Published by Merative (TPA), schema 2.0.0. Two in-network files: HMO zip, OHIC zip. Many plans → same file.
- HMO: 474 MB zipped, 5.87 GB unzipped, single JSON, in `data/`. OHIC not downloaded yet.
- Header: reporting_entity_type "Third-Party Administrator", last_updated_on 2026-10-01, version 2.0.0.
- Same layout as KP: header → `provider_references` → `in_network`. Same double-explode flatten.
- `provider_references` entries carry `network_name[]` (e.g. DIRECT, SELECT, VCUEMP) → candidate column on `provider_group`.
- First record: CPT 0006M, 68 negotiated_rates; first one maps 5,490 provider groups to a single price → heavy fan-out on explode.
- negotiated_prices carry `service_code[]` (place-of-service codes) — not in planned silver model yet.

### CareFirst (replaces Anthem)
- Index host: `stmrffilesprod001.blob.core.windows.net/mrf-files/` (see `data_sources.md`). Container listing blocked; discover via page HTML.
- In-network files are `.json.gz` split into parts (`_10_of_35`). PPO/FEHBP parts 14-34 MB; "National" HMO parts up to 1.4 GB (skipped).
- Signed URLs on `carefirstbcbs.mrf.bcbs.com` expire (~1 month). Always re-read the index.
- Same layout as KP/Sentara. One PPO part: 609 billing codes.

### Anthem (deferred)
- National index on S3: `.../anthem/YYYY-MM-01_anthem_index.json.gz`. Huge. Not started.

---

## Data quality / standardization log
1. KP `billing_code_type` = "FY2026" (CMS expects "MS-DRG"); real type in `billing_code_type_version` ("FY2026 MS DRG V43.0"). Possibly deliberate (DRGs change yearly) → standardization rule, keep raw.
2. `negotiated_rate` arrives as a string → cast to DECIMAL(18,2).
3. KP plan_id not unique (same HIOS id, multiple CSR-variant names) → key on plan_id + plan_name.
4. KP file has 3 dates: filename 2026-10-01, index 2026-09-17, header 2026-09-01.
5. Schema version drift: KP 2.0.1 vs Sentara 2.0.0.
6. KP plan_id_type mixes `hios` and `ein` across indexes.
7. KP self-funded index reporting_entity_type = "Health Insurance Issuer" vs "Group Health Plan" in the others.
8. Reston Hospital has no `cms-hpt.txt` on its own domain (404).
9. Hospital formats vary: Inova CSV, Sentara XLSX, VHC vendor portal, HCA JSON.
10. `negotiated_rate` JSON type differs by insurer: Sentara = number (`0.00`), KP = string. Cast must handle both.
11. Sentara has $0.00 negotiated rates (first record). Flag in DQ, don't silently drop.
12. Sentara `expiration_date` = `9999-12-31` sentinel ("no expiry") → null or keep, decide in silver.
13. Sentara CPT `billing_code_type_version` = "10" (not a real CPT version) → standardization rule, keep raw.
14. Same TIN in two formats within one provider group: `541581185` vs `54-1581185` → strip dashes.
15. `service_code[]` array on negotiated_prices not in planned `negotiated_rate` columns.
16. CareFirst schema `version` = "1.2.0" (KP 2.0.1, Sentara 2.0.0).
17. CareFirst header `last_updated_on` = "2020-08-27" on 2026-10 files. Don't trust header date; use filename / index date.
18. CareFirst `name` is a category ("Surgery" for CPT 57452), not a description. Need a CPT description source in silver.
19. `billing_code_modifier` (all 3) and `bundled_codes` (KP) not in planned silver model -> added.
20. `provider_group_id` is unique only within a file. Key = source_file + provider_group_id.
21. CareFirst: 1,281 of 23,953 TIN entries have no `business_name` (PPO part 10). Name lookup must come from NPI registry.
22. Same NPI under several businesses is common: 28,335 of 99,956 NPIs (CareFirst PPO part 10). A doctor can have different rates per organization.
