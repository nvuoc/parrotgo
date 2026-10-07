"""Data ingestion and validation CLI."""

import argparse
import json
import sys
from pathlib import Path

from src.config import settings
from src.db.in_memory_cache import geo_cache
from src.db.chroma_client import chroma_faq_client


def load_json_file(file_path: str):
    p = Path(file_path)
    if not p.exists():
        print(f"Error: File '{file_path}' does not exist.", file=sys.stderr)
        sys.exit(1)
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def cmd_validate_places(args):
    data = load_json_file(args.input)
    try:
        geo_cache.validate_dataset(data)
        places_count = len(data.get("places", []))
        aliases_count = len(data.get("aliases", []))
        gates_count = len(data.get("gates", []))
        streets_count = len(data.get("streets", []))
        print(
            f"Validation SUCCESS: {places_count} places, {aliases_count} aliases, "
            f"{gates_count} gates, {streets_count} streets valid."
        )
    except Exception as e:
        print(f"Validation FAILED: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_upsert_places(args):
    data = load_json_file(args.input)
    try:
        snapshot = Path(settings.GEO_DATA_PATH)
        if snapshot.exists():
            geo_cache.hydrate_snapshot(snapshot)
        geo_cache.upsert_dataset(data)
        geo_cache.persist_snapshot(snapshot)
        places_count = len(data.get("places", []))
        print(f"Upsert SUCCESS: {places_count} places processed.")
    except Exception as e:
        print(f"Upsert FAILED: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_validate_faq(args):
    data = load_json_file(args.input)
    if not isinstance(data, list):
        print("Validation FAILED: FAQ file must contain a JSON list of chunks.", file=sys.stderr)
        sys.exit(1)
    try:
        chroma_faq_client.validate_chunks(data)
        print(f"Validation SUCCESS: {len(data)} FAQ chunks valid.")
    except Exception as e:
        print(f"Validation FAILED: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_upsert_faq(args):
    data = load_json_file(args.input)
    if not isinstance(data, list):
        print("Upsert FAILED: FAQ file must contain a JSON list of chunks.", file=sys.stderr)
        sys.exit(1)
    try:
        count = chroma_faq_client.upsert_faq_policies(data)
        print(f"Upsert SUCCESS: {count} FAQ chunks upserted.")
    except Exception as e:
        print(f"Upsert FAILED: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_export_places(args):
    try:
        snapshot = Path(settings.GEO_DATA_PATH)
        if snapshot.exists():
            geo_cache.hydrate_snapshot(snapshot)
        data = geo_cache.export_dataset()
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Export SUCCESS: saved to {args.output}")
    except Exception as e:
        print(f"Export FAILED: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="ParrotGo Data Ingestion & Validation CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # validate-places
    p_val_places = subparsers.add_parser("validate-places", help="Validate places dataset JSON")
    p_val_places.add_argument("--input", required=True, help="Input JSON file path")
    p_val_places.set_defaults(func=cmd_validate_places)

    # upsert-places
    p_ups_places = subparsers.add_parser("upsert-places", help="Upsert places dataset into cache")
    p_ups_places.add_argument("--input", required=True, help="Input JSON file path")
    p_ups_places.set_defaults(func=cmd_upsert_places)

    # validate-faq
    p_val_faq = subparsers.add_parser("validate-faq", help="Validate FAQ chunks JSON")
    p_val_faq.add_argument("--input", required=True, help="Input JSON file path")
    p_val_faq.set_defaults(func=cmd_validate_faq)

    # upsert-faq
    p_ups_faq = subparsers.add_parser("upsert-faq", help="Upsert FAQ chunks into Chroma")
    p_ups_faq.add_argument("--input", required=True, help="Input JSON file path")
    p_ups_faq.set_defaults(func=cmd_upsert_faq)

    # export-places
    p_exp_places = subparsers.add_parser("export-places", help="Export places dataset snapshot")
    p_exp_places.add_argument("--output", required=True, help="Output JSON file path")
    p_exp_places.set_defaults(func=cmd_export_places)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
