"""Flatten CMS in-network MRFs into two Parquet tables per source file.

Design: docs/design_flatten.md

Input layout:  data/<insurer>/<yyyy-mm>/<file>.zip | .json.gz
Output layout: <out>/<insurer>/<yyyy-mm>/<source_stem>/{provider_group,negotiated_rate}.parquet
Run log:       <out>/_runs/flatten_runs.jsonl

Restructure only: every value is written as text, nothing is cast or fixed.

Usage:
    python -m ingest.flatten data/carefirst/2026-10/*.json.gz --limit 50
"""

import argparse
import contextlib
import glob
import gzip
import json
import logging
import os
import re
import shutil
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import ijson
import pyarrow as pa
import pyarrow.parquet as pq

log = logging.getLogger("flatten")

BATCH_SIZE = 50_000

FILE_COLUMNS = [
    "insurer", "source_file", "file_month", "filename_date",
    "header_last_updated", "header_version",
]

_str = pa.string()
_list = pa.list_(pa.string())

PROVIDER_GROUP_SCHEMA = pa.schema(
    [(c, _str) for c in FILE_COLUMNS]
    + [
        ("provider_group_id", _str),
        ("network_name", _list),
        ("tin_type", _str),
        ("tin_value", _str),
        ("business_name", _str),
        ("npi", _list),
    ]
)

NEGOTIATED_RATE_SCHEMA = pa.schema(
    [(c, _str) for c in FILE_COLUMNS]
    + [
        ("billing_code_type", _str),
        ("billing_code_type_version", _str),
        ("billing_code", _str),
        ("name", _str),
        ("description", _str),
        ("negotiation_arrangement", _str),
        ("provider_group_ids", _list),
        ("negotiated_type", _str),
        ("negotiated_rate", _str),
        ("expiration_date", _str),
        ("billing_class", _str),
        ("setting", _str),
        ("service_code", _list),
        ("billing_code_modifier", _list),
        ("bundled_codes", _str),
    ]
)

# Fields we know how to map. Anything else is listed in the run log, not dropped silently.
TOP_KEYS = {"reporting_entity_name", "reporting_entity_type", "last_updated_on", "version",
            "provider_references", "in_network"}
REF_KEYS = {"provider_group_id", "network_name", "provider_groups", "location"}
GROUP_KEYS = {"npi", "tin"}
ITEM_KEYS = {"negotiation_arrangement", "name", "billing_code_type", "billing_code_type_version",
             "billing_code", "description", "negotiated_rates", "bundled_codes"}
RATE_KEYS = {"provider_references", "negotiated_prices"}
PRICE_KEYS = {"negotiated_type", "negotiated_rate", "expiration_date", "service_code",
              "billing_class", "setting", "billing_code_modifier"}

COMPRESSED_SUFFIXES = (".json.gz", ".zip")


# ---------- small helpers ----------

def to_str(value):
    """Text as-is. ijson gives Decimal for numbers, so str() keeps '146.77' / '0.00' exact."""
    return None if value is None else str(value)


def to_str_list(values):
    return None if values is None else [to_str(v) for v in values]


def note_unknown(obj, known, level, stats):
    for key in obj.keys() - known:
        stats["unknown_fields"].add(f"{level}.{key}")


def source_stem(path):
    name = path.name
    for suffix in COMPRESSED_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    raise ValueError(f"unsupported file type: {name} (expected .zip or .json.gz)")


# ---------- reading ----------

@contextlib.contextmanager
def open_stream(path):
    """Binary stream of the JSON inside a .zip or .json.gz. Never unzips to disk."""
    if path.name.endswith(".json.gz"):
        with gzip.open(path, "rb") as fh:
            yield fh
    elif path.name.endswith(".zip"):
        with zipfile.ZipFile(path) as zf:
            members = [m for m in zf.namelist() if m.lower().endswith(".json")]
            if len(members) != 1:
                raise ValueError(f"{path.name}: expected exactly 1 JSON inside zip, found {members}")
            with zf.open(members[0]) as fh:
                yield fh
    else:
        raise ValueError(f"unsupported file type: {path.name}")


def read_header(path, stats):
    """File-level columns: insurer/month from the folder names, header fields from the file top."""
    match = re.search(r"\d{4}-\d{2}(-\d{2})?", path.name)
    meta = {
        "insurer": path.parent.parent.name,
        "source_file": path.name,
        "file_month": path.parent.name,
        "filename_date": match.group(0) if match else None,
        "header_last_updated": None,
        "header_version": None,
    }
    header = {}
    with open_stream(path) as fh:
        for prefix, event, value in ijson.parse(fh):
            if prefix == "" and event == "map_key":
                if value not in TOP_KEYS:
                    stats["unknown_fields"].add(f"top.{value}")
            elif prefix in TOP_KEYS and event in ("string", "number"):
                header[prefix] = value
            elif prefix in ("provider_references", "in_network") and event == "start_array":
                break
    meta["header_last_updated"] = to_str(header.get("last_updated_on"))
    meta["header_version"] = to_str(header.get("version"))
    return meta


def iter_provider_groups(stream, meta, stats):
    """Pass 1: one row per provider group per TIN."""
    for ref in ijson.items(stream, "provider_references.item"):
        note_unknown(ref, REF_KEYS, "provider_references", stats)
        if "provider_groups" not in ref:
            if "location" in ref:
                stats["remote_refs"] += 1
                log.warning("%s: remote provider reference skipped: %s",
                            meta["source_file"], ref["location"])
            continue
        for group in ref["provider_groups"]:
            note_unknown(group, GROUP_KEYS, "provider_groups", stats)
            tin = group.get("tin") or {}
            yield {
                **meta,
                "provider_group_id": to_str(ref.get("provider_group_id")),
                "network_name": to_str_list(ref.get("network_name")),
                "tin_type": to_str(tin.get("type")),
                "tin_value": to_str(tin.get("value")),
                "business_name": to_str(tin.get("business_name")),
                "npi": to_str_list(group.get("npi")),
            }


def price_fields(price, stats):
    """Columns that come from one negotiated_prices entry."""
    note_unknown(price, PRICE_KEYS, "negotiated_prices", stats)
    return {
        "negotiated_type": to_str(price.get("negotiated_type")),
        "negotiated_rate": to_str(price.get("negotiated_rate")),
        "expiration_date": to_str(price.get("expiration_date")),
        "billing_class": to_str(price.get("billing_class")),
        "setting": to_str(price.get("setting")),
        "service_code": to_str_list(price.get("service_code")),
        "billing_code_modifier": to_str_list(price.get("billing_code_modifier")),
    }


def iter_rates(stream, meta, stats, limit=None):
    """Pass 2: one row per billing code x rate block x price."""
    for item in ijson.items(stream, "in_network.item"):
        if limit is not None and stats["in_network_items"] >= limit:
            break
        stats["in_network_items"] += 1
        note_unknown(item, ITEM_KEYS, "in_network", stats)
        bundled = item.get("bundled_codes")
        code = {
            **meta,
            "billing_code_type": to_str(item.get("billing_code_type")),
            "billing_code_type_version": to_str(item.get("billing_code_type_version")),
            "billing_code": to_str(item.get("billing_code")),
            "name": to_str(item.get("name")),
            "description": to_str(item.get("description")),
            "negotiation_arrangement": to_str(item.get("negotiation_arrangement")),
            "bundled_codes": json.dumps(bundled, default=str) if bundled is not None else None,
        }

        # TODO(human): unpack the two nested levels into rows.
        # item["negotiated_rates"] is a list of rate blocks. Each block has
        #   "provider_references": list of group ids   -> one list column "provider_group_ids"
        #   "negotiated_prices":   list of price dicts -> one output row per price
        # For each row: yield {**code, "provider_group_ids": ..., **price_fields(price, stats)}
        # A block with no ids or no prices writes no row: add 1 to stats["empty_blocks"].
        # Also call note_unknown(block, RATE_KEYS, "negotiated_rates", stats) per block.
        # See ingest/walkthrough_rates.py cells 6-7: same idea, with one more loop around it.
        # "yield row" = hand one row to the writer (like rows.append(row), without keeping them all).


# ---------- writing ----------

class BatchWriter:
    """Buffers row dicts and writes them to one Parquet file in batches, with a fixed schema."""

    def __init__(self, path, schema, batch_size=BATCH_SIZE):
        self.schema = schema
        self.batch_size = batch_size
        self.rows = 0
        self._buffer = []
        self._writer = pq.ParquetWriter(path, schema)

    def add(self, row):
        self._buffer.append(row)
        if len(self._buffer) >= self.batch_size:
            self._flush()

    def _flush(self):
        if self._buffer:
            self._writer.write_table(pa.Table.from_pylist(self._buffer, schema=self.schema))
            self.rows += len(self._buffer)
            self._buffer = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self._flush()
        self._writer.close()


# ---------- one file ----------

def new_stats():
    return {"in_network_items": 0, "remote_refs": 0, "empty_blocks": 0, "unknown_fields": set()}


def flatten_file(path, out_root, limit=None, force=False):
    """All-or-nothing: write into a sibling _tmp folder, rename to the final folder on success."""
    started = time.monotonic()
    stats = new_stats()
    result = {"source_file": path.name, "status": None, "provider_group_rows": 0,
              "negotiated_rate_rows": 0, "error": None}

    stem = source_stem(path)
    month_dir = out_root / path.parent.parent.name / path.parent.name
    final_dir = month_dir / stem
    tmp_dir = month_dir / f"{stem}__tmp"

    if final_dir.exists() and not force:
        result["status"] = "skipped"
    else:
        shutil.rmtree(tmp_dir, ignore_errors=True)  # leftover from a crash
        tmp_dir.mkdir(parents=True)
        try:
            meta = read_header(path, stats)
            with open_stream(path) as fh, \
                    BatchWriter(tmp_dir / "provider_group.parquet", PROVIDER_GROUP_SCHEMA) as w:
                for row in iter_provider_groups(fh, meta, stats):
                    w.add(row)
            result["provider_group_rows"] = w.rows

            with open_stream(path) as fh, \
                    BatchWriter(tmp_dir / "negotiated_rate.parquet", NEGOTIATED_RATE_SCHEMA) as w:
                for row in iter_rates(fh, meta, stats, limit):
                    w.add(row)
            result["negotiated_rate_rows"] = w.rows

            if final_dir.exists():  # --force: Windows cannot rename over an existing folder
                shutil.rmtree(final_dir)
            tmp_dir.rename(final_dir)
            result["status"] = "ok"
        except Exception as exc:  # one bad file must not stop the run
            shutil.rmtree(tmp_dir, ignore_errors=True)
            result["status"] = "failed"
            result["error"] = f"{type(exc).__name__}: {exc}"
            log.exception("%s failed", path.name)

    result.update(
        in_network_items=stats["in_network_items"],
        remote_refs=stats["remote_refs"],
        empty_blocks=stats["empty_blocks"],
        unknown_fields=sorted(stats["unknown_fields"]),
        limit=limit,
        seconds=round(time.monotonic() - started, 1),
        run_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    return result


# ---------- CLI ----------

def main(argv=None):
    parser = argparse.ArgumentParser(description="Flatten CMS in-network MRFs to Parquet.")
    parser.add_argument("inputs", nargs="+", type=Path, help="data/<insurer>/<yyyy-mm>/<file>")
    parser.add_argument("--out", type=Path, default=Path(os.environ.get("FLATTEN_OUT_DIR", "out")),
                        help="output root (default: env FLATTEN_OUT_DIR or ./out)")
    parser.add_argument("--limit", type=int, default=None,
                        help="stop after N in_network items (quick tests)")
    parser.add_argument("--force", action="store_true", help="rebuild files already flattened")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_log = args.out / "_runs" / "flatten_runs.jsonl"
    run_log.parent.mkdir(parents=True, exist_ok=True)

    # PowerShell does not expand wildcards for python, so expand them here.
    paths = []
    for arg in args.inputs:
        matches = sorted(glob.glob(str(arg)))
        paths.extend(Path(m) for m in matches) if matches else paths.append(arg)

    failed = 0
    for path in paths:
        if not path.is_file() or not path.name.endswith(COMPRESSED_SUFFIXES):
            log.warning("not an in-network .zip/.json.gz file, skipped: %s", path)
            continue
        log.info("start %s", path.name)
        result = flatten_file(path, args.out, args.limit, args.force)
        with run_log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(result) + "\n")
        log.info("%s %s: %s groups, %s rates, %s codes, %ss", result["status"], path.name,
                 result["provider_group_rows"], result["negotiated_rate_rows"],
                 result["in_network_items"], result["seconds"])
        failed += result["status"] == "failed"
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
