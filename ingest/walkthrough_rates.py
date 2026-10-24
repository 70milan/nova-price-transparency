# Walkthrough of flatten pass 2 (prices). No functions: read it top to bottom.
#
# Run one cell at a time in Cursor: click "Run Cell" above each "# %%" line (or Shift+Enter).
# Or run everything at once from the repo root:  python ingest/walkthrough_rates.py
#
# It reads only the FIRST billing code of one CareFirst file, so each cell is instant.

# %% 1. Open the file and take the first billing code
import gzip
import json
from pathlib import Path

import ijson

here = Path.cwd()
repo = here if (here / "data").exists() else here.parent   # works from repo root or ingest/
path = repo / "data/carefirst/2026-10/2026-10_690_08B0_in-network-rates_10_of_35.json.gz"

fh = gzip.open(path, "rb")                   # read the .gz without unzipping to disk
items = ijson.items(fh, "in_network.item")   # a stream that hands out one billing code at a time
item = next(items)                           # take the first one and stop reading

print("keys of one billing code:", list(item.keys()))

# %% 2. Code-level fields: the same for every row this code produces
print("billing_code_type:", item["billing_code_type"])
print("billing_code     :", item["billing_code"])
print("name             :", item["name"])

# %% 3. negotiated_rates = the list of rate blocks for this code
blocks = item["negotiated_rates"]
print("rate blocks for this code:", len(blocks))

block = blocks[0]                            # [0] = first element of a list
print("first block, as JSON:")
print(json.dumps(block, default=str))     # one long line; service_code = place-of-service codes

# %% 4. Inside one block: WHO (group ids) and WHAT PRICES
ids = block["provider_references"]           # list of group ids
prices = block["negotiated_prices"]          # list of price dicts

print("group ids:", ids)
print("prices in this block:", len(prices))
for price in prices:                         # for loop = run the indented lines once per price
    print("  rate", price["negotiated_rate"], "|", price["billing_class"], "|", price["setting"])

# %% 5. Build ONE output row by hand (block 0, price 0)
price = prices[0]

code_part = {                                # columns from the billing code (cell 2)
    "billing_code": str(item["billing_code"]),
    "name": item["name"],
}
price_part = {                               # columns from one price (cell 4)
    "negotiated_rate": str(price["negotiated_rate"]),
    "billing_class": price.get("billing_class"),   # .get = None instead of crash if missing
    "setting": price.get("setting"),
}

# {**a, **b} glues two dicts into one, like SELECT a.*, b.* in SQL
row = {**code_part, "provider_group_ids": [str(i) for i in ids], **price_part}
print(row)

# %% 6. One row PER PRICE in this block: the same as cell 5, inside a loop
rows = []
for price in prices:
    price_part = {
        "negotiated_rate": str(price["negotiated_rate"]),
        "billing_class": price.get("billing_class"),
        "setting": price.get("setting"),
    }
    rows.append({**code_part, "provider_group_ids": [str(i) for i in ids], **price_part})

print("rows from block 0:", len(rows))
for r in rows:
    print(" ", r)

# %% 7. Your TODO in flatten.py = cell 6, but for EVERY block (a loop around the loop)
expected = 0
for b in blocks:
    expected = expected + len(b["negotiated_prices"])

print("blocks:", len(blocks), "| rows your loop should produce for this one code:", expected)

# %% 8. Close the file
fh.close()
