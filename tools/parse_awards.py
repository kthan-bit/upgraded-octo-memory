#!/usr/bin/env python3
"""Normalize a manually saved Air Canada award-search response."""

import argparse
from datetime import date
import json
from pathlib import Path
import re
import sys
from typing import Any


CABINS = {
    "E": "economy",
    "P": "premium",
    "B": "business",
    "F": "first",
}
VALID_CABINS = tuple(CABINS.values())
AIRPORT_CODE = re.compile(r"^[A-Z]{3}$")


class ParseError(ValueError):
    """Raised when the saved response does not match the expected schema."""


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _required_text(record: dict[str, Any], key: str, context: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise ParseError(f"{context} is missing a non-empty {key!r} field")
    return value


def _required_integer(record: dict[str, Any], key: str, context: str) -> int:
    value = record.get(key)
    if isinstance(value, bool):
        raise ParseError(f"{context} has an invalid {key!r} value")
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ParseError(f"{context} has an invalid {key!r} value") from error


def _normalize_segment(raw_segment: Any, index: int) -> dict[str, Any]:
    context = f"segment {index}"
    if not isinstance(raw_segment, dict):
        raise ParseError(f"{context} must be a JSON object")

    cabin_code = _required_text(raw_segment, "cabin", context)
    if cabin_code not in CABINS:
        raise ParseError(f"{context} has an unsupported cabin code {cabin_code!r}")

    return {
        "airline": _required_text(raw_segment, "airline", context),
        "flight_number": _required_text(raw_segment, "flightNo", context),
        "aircraft": raw_segment.get("product"),
        "origin": _required_text(raw_segment, "origin", context),
        "destination": _required_text(raw_segment, "destination", context),
        "departure": _required_text(raw_segment, "departureDateTime", context),
        "arrival": _required_text(raw_segment, "arrivalDateTime", context),
        "cabin": CABINS[cabin_code],
        "stops": _required_integer(raw_segment, "stop", context),
        "lag_days": _required_integer(raw_segment, "lagDays", context),
    }


def validate_query(origin: str, destination: str, depart_date: str, cabin: str) -> dict[str, str]:
    origin = origin.upper()
    destination = destination.upper()
    if not AIRPORT_CODE.fullmatch(origin):
        raise ParseError("origin must be a three-letter airport code")
    if not AIRPORT_CODE.fullmatch(destination):
        raise ParseError("destination must be a three-letter airport code")
    try:
        parsed_date = date.fromisoformat(depart_date)
    except ValueError as error:
        raise ParseError("date must use YYYY-MM-DD format") from error
    if parsed_date.isoformat() != depart_date:
        raise ParseError("date must use YYYY-MM-DD format")
    if cabin not in VALID_CABINS:
        raise ParseError(f"cabin must be one of: {', '.join(VALID_CABINS)}")

    return {
        "origin": origin,
        "destination": destination,
        "date": depart_date,
        "cabin": cabin,
    }


def parse_response(
    payload: Any,
    query: dict[str, str],
    *,
    strict: bool = True,
) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ParseError("input must be a JSON object")
    normal_results = payload.get("NormalResults")
    if not isinstance(normal_results, dict):
        raise ParseError("input is missing the NormalResults object")
    products = normal_results.get("product")
    if products is None:
        raise ParseError("input is missing NormalResults.product")

    awards: list[dict[str, Any]] = []
    for product in _as_list(products):
        if not isinstance(product, dict):
            raise ParseError("each NormalResults.product entry must be a JSON object")
        product_name = product.get("name")
        if product_name not in ("classic", "classicPlus"):
            continue

        for component in _as_list(product.get("tripComponent")):
            if not isinstance(component, dict):
                raise ParseError(f"{product_name} tripComponent entries must be JSON objects")
            if str(component.get("position")) != "0":
                continue

            for option in _as_list(component.get("ODoption")):
                if not isinstance(option, dict):
                    raise ParseError(f"{product_name} ODoption entries must be JSON objects")
                raw_segments = option.get("segment")
                if raw_segments is None:
                    raise ParseError(f"{product_name} ODoption is missing its segment list")
                segments = [
                    _normalize_segment(segment, index)
                    for index, segment in enumerate(_as_list(raw_segments), start=1)
                ]
                if not segments:
                    raise ParseError(f"{product_name} ODoption has no segments")

                if query.get("origin") and segments[0]["origin"] != query["origin"]:
                    if strict:
                        raise ParseError("response origin does not match --from")
                    continue
                if query.get("destination") and segments[-1]["destination"] != query["destination"]:
                    if strict:
                        raise ParseError("response destination does not match --to")
                    continue
                expected_date = query.get("date")
                if expected_date and not segments[0]["departure"].startswith(expected_date):
                    if strict:
                        raise ParseError("response departure date does not match --date")
                    continue

                mileage = _required_integer(option, "startingMileage", f"{product_name} ODoption")
                if mileage < 0:
                    raise ParseError(f"{product_name} ODoption has a negative startingMileage")

                awards.append({
                    "fare_type": "fixed" if product_name == "classic" else "market",
                    "mileage_cost": mileage,
                    "cabin": query["cabin"],
                    "segments": segments,
                })

    return awards


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize a manually saved Air Canada award response to JSON."
    )
    parser.add_argument("input", help="Saved response JSON path, or '-' to read stdin")
    parser.add_argument("--from", dest="origin", required=True, help="Origin IATA airport code")
    parser.add_argument("--to", dest="destination", required=True, help="Destination IATA airport code")
    parser.add_argument("--date", required=True, help="Departure date (YYYY-MM-DD)")
    parser.add_argument("--cabin", required=True, choices=VALID_CABINS)
    parser.add_argument("--output", help="Output path; defaults to stdout")
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    try:
        query = validate_query(args.origin, args.destination, args.date, args.cabin)
        if args.input == "-":
            payload = json.load(sys.stdin)
        else:
            payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
        output = {
            "query": query,
            "awards": parse_response(payload, query),
        }
        rendered = json.dumps(output, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            Path(args.output).write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
    except (OSError, json.JSONDecodeError, ParseError) as error:
        print(f"parse-awards: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
