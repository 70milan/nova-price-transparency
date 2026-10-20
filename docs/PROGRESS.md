# Progress Log

## Next step
1. Commit + push Day 2 work (`data/` confirmed gitignored; `docs/PROGRESS.md` still untracked).
2. Start `ingest/flatten.py`: stream from zip with ijson → write `provider_group` + `negotiated_rate` Parquet. Test on Sentara HMO first.

## Open items
- KP: `-04` / `-07` files optional; later test whether they're near-duplicates of `-01`.
- KP: how many provider groups are NoVA hospitals? Needs NPI lookup.
- Anthem: not started. Stream national index, keep only VA in-network URLs.
- Hospitals: UVA Prince William / Haymarket MRF not found. Reston/StoneSprings current HCA links need verifying.
- Nothing uploaded to Azure yet.

---

## Day log

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

### Anthem
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