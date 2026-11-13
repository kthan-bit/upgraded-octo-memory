#!/usr/bin/env python3
"""Search locally saved Air Canada response JSON files."""

import argparse
from datetime import date
import json
from pathlib import Path
import sys
from typing import Any

from tools.parse_awards import ParseError, VALID_CABINS, parse_response, validate_query


DEFAULT_RESPONSE_DIR = Path(__file__).resolve().parents[1] / "data" / "responses"


def search_awards(
    airport_from: str,
    airport_to: str,
    date_start: str,
    date_end: str,
    cabin_class: str,
    response_dir: str | Path = DEFAULT_RESPONSE_DIR,
) -> dict[str, Any]:
    """Filter manually saved response files for a route, date range, and cabin."""
    query = validate_query(airport_from, airport_to, date_start, cabin_class.lower())
    try:
        end = date.fromisoformat(date_end)
    except ValueError as error:
        raise ParseError("end date must use YYYY-MM-DD format") from error
    if end.isoformat() != date_end:
        raise ParseError("end date must use YYYY-MM-DD format")
    if end < date.fromisoformat(date_start):
        raise ParseError("end date must be on or after start date")

    directory = Path(response_dir)
    if not directory.is_dir():
        raise FileNotFoundError(f"response directory does not exist: {directory}")
    response_files = sorted(directory.glob("*.json"))
    if not response_files:
        raise FileNotFoundError(f"no response JSON files found in: {directory}")

    awards_by_key: dict[str, dict[str, Any]] = {}
    for response_file in response_files:
        try:
            payload = json.loads(response_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ParseError(f"{response_file.name} is not valid JSON: {error.msg}") from error

        parsed_awards = parse_response(
            payload,
            {
                "origin": query["origin"],
                "destination": query["destination"],
                "cabin": query["cabin"],
            },
            strict=False,
        )
        for award in parsed_awards:
            departure = award["segments"][0]["departure"]
            departure_date = departure[:10]
            if not date_start <= departure_date <= date_end:
                continue
            if any(segment["cabin"] != query["cabin"] for segment in award["segments"]):
                continue

            award["departure_date"] = departure_date
            key = json.dumps(award, sort_keys=True, separators=(",", ":"))
            awards_by_key[key] = award

    return {
        "query": {
            "origin": query["origin"],
            "destination": query["destination"],
            "date_start": date_start,
            "date_end": date_end,
            "cabin": query["cabin"],
        },
        "awards": list(awards_by_key.values()),
    }


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search a local folder of manually saved award-response JSON files."
    )
    parser.add_argument("--from", dest="airport_from", required=True, help="Origin IATA code")
    parser.add_argument("--to", dest="airport_to", required=True, help="Destination IATA code")
    parser.add_argument("--start", dest="date_start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", dest="date_end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--cabin", required=True, choices=VALID_CABINS)
    parser.add_argument(
        "--response-dir",
        type=Path,
        default=DEFAULT_RESPONSE_DIR,
        help=f"Folder containing saved response JSON files (default: {DEFAULT_RESPONSE_DIR})",
    )
    parser.add_argument("--output", type=Path, help="Output path; defaults to stdout")
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    try:
        output = search_awards(
            airport_from=args.airport_from,
            airport_to=args.airport_to,
            date_start=args.date_start,
            date_end=args.date_end,
            cabin_class=args.cabin,
            response_dir=args.response_dir,
        )
        rendered = json.dumps(output, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            args.output.write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
    except (OSError, ParseError) as error:
        print(f"search-local-awards: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
