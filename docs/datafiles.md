# Data Sources — NoVA Price Transparency

Pulled 2026-10-19. Re-verify links monthly (insurer files) / annually (hospital files).

## Insurers (Transparency in Coverage MRFs)

### Sentara Health Plans — START HERE (smallest, cleanest)
- Landing page: https://www.sentarahealthplans.com/en/vendor/machine-readable-data
- Index (TOC), Oct 2026: https://mrfproddestinationdata.blob.core.windows.net/sentara-mrf-output/2026-10-01_Sentara-INN_index.json
- Only 2 in-network files referenced by the index:
  - https://mrfproddestinationdata.blob.core.windows.net/sentara-mrf-output/2026-10-01_Sentara-Health-Plans_HMO_in-network-rates.zip
  - https://mrfproddestinationdata.blob.core.windows.net/sentara-mrf-output/2026-10-01_Sentara-Health-Plans_OHIC_in-network-rates.zip
- Notes: published by Merative (TPA) on behalf of Sentara; schema version 2.0.0; .zip not .json.gz; hosted on Azure Blob (same cloud as us).
- Index has hundreds of employer plans pointing at the same 2 files → plan-to-file is many-to-one (model as a bridge table).

### Anthem (BCBS Virginia) — BIGGEST, scope it down
- Search page: https://www.anthem.com/machine-readable-file/search/
- National index pattern (Aug 2026 confirmed): https://antm-pt-prod-dataz-nogbd-nophi-us-east1.s3.amazonaws.com/anthem/2026-08-01_anthem_index.json.gz
- Oct 2026 should be the same path with 2026-10-01 (VERIFY before use).
- The index itself is huge. Stream it (ijson), never load into memory. Pull only Virginia in-network file URLs.

### Kaiser Permanente — Mid-Atlantic States region (MD/VA/DC)
- Page: https://healthy.kaiserpermanente.org/front-door/machine-readable → "Mid-Atlantic States" section
- File list loads via JavaScript — open in browser, copy the Mid-Atlantic in-network + TOC links manually.
- Expect thin per-service pricing (closed-panel model). That gap is a finding, not a bug.

## Hospitals (Hospital Price Transparency MRFs)

| Hospital | System | Format | MRF URL |
|---|---|---|---|
| Inova Fairfax | Inova | CSV | https://www.inova.org/sites/default/files/patient_visitor/price_transparency/2026/540620889_inova-fairfax-hospital_standardcharges.csv |
| Inova Fair Oaks | Inova | CSV | https://www.inova.org/sites/default/files/patient_visitor/price_transparency/2026/540620889_inova-fair-oaks-hospital_standardcharges.csv |
| Inova Alexandria | Inova | CSV | https://www.inova.org/sites/default/files/patient_visitor/price_transparency/2026/540620889_inova-alexandria-hospital_standardcharges.csv |
| Inova Loudoun | Inova | CSV | https://www.inova.org/sites/default/files/patient_visitor/price_transparency/2026/540620889_inova-loudoun-hospital_standardcharges.csv |
| Inova Mount Vernon | Inova | CSV | https://www.inova.org/sites/default/files/patient_visitor/price_transparency/2026/540620889_inova-mount-vernon-hospital_standardcharges.csv |
| VHC Health (Arlington) | Independent | via Panacea (check type) | https://vhchealth.pt.panaceainc.com/MRFDownload/vhchealth/virginiahospitalcenter |
| Sentara Northern Virginia (Woodbridge) + Lake Ridge | Sentara | XLSX link | https://www.sentara.com/Documents/s/sentaranorthernvirginiamedicalcenterstandardchargesxlsx-1395275 |
| Reston Hospital Center | HCA | JSON (~340 MB, late 2025) | https://www.hcadam.com/api/public/content/977c855a86684e33923858d0335f1e99?download=true (VERIFY current link) |
| StoneSprings (Dulles) | HCA | JSON | from https://www.hcavirginia.com/patient-resources/patient-financial-resources/pricing-transparency-cms-required-file-of-standard-charges |
| UVA Health Prince William / Haymarket | UVA | TBD | not found yet |

Discovery files: inova.org/cms-hpt.txt, sentara.com/cms-hpt.txt, vhchealth.org/cms-hpt.txt
(Reston has no cms-hpt.txt at its own domain → 404. Itself a compliance finding.)

## Why this mix is good for the project
- 4 different hospital formats (CSV, JSON, XLSX, vendor portal) → bronze must handle each; silver normalizes to one schema.
- Sentara Northern Virginia and Lake Ridge share one file → one file, many locations.
- Sentara is both an insurer and a hospital system → clean insurer-vs-hospital rate mismatch test case.
- Inova files are all EIN 540620889 → join key across hospital and insurer data (TIN).