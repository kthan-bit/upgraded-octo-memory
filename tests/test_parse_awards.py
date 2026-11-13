import copy
import json
from pathlib import Path
import tempfile
import unittest

from tools.parse_awards import ParseError, parse_response, validate_query
from tools.search_local_awards import search_awards


QUERY = validate_query("fco", "ewr", "2026-12-12", "economy")


def segment(**overrides):
    value = {
        "airline": "AC",
        "flightNo": "AC 123",
        "product": "789",
        "origin": "FCO",
        "destination": "EWR",
        "departureDateTime": "2026-12-12T10:00:00",
        "arrivalDateTime": "2026-12-12T14:00:00",
        "cabin": "E",
        "stop": "0",
        "lagDays": "0",
    }
    return {**value, **overrides}


def response():
    return {
        "NormalResults": {
            "product": [
                {
                    "name": "classic",
                    "tripComponent": [{
                        "position": 0,
                        "ODoption": [{
                            "startingMileage": 50000,
                            "segment": [segment()],
                        }],
                    }],
                },
                {
                    "name": "classicPlus",
                    "tripComponent": [{
                        "position": 0,
                        "ODoption": [{
                            "startingMileage": "82000",
                            "segment": [segment(flightNo="AC 456", cabin="B")],
                        }],
                    }],
                },
                {
                    "name": "regular",
                    "tripComponent": [{
                        "position": 0,
                        "ODoption": [{
                            "startingMileage": 1,
                            "segment": [segment()],
                        }],
                    }],
                },
            ],
        },
    }


class ParseAwardsTests(unittest.TestCase):
    def test_normalizes_fixed_and_market_awards(self):
        awards = parse_response(response(), QUERY)

        self.assertEqual(len(awards), 2)
        self.assertEqual(awards[0]["fare_type"], "fixed")
        self.assertEqual(awards[0]["mileage_cost"], 50000)
        self.assertEqual(awards[0]["segments"][0]["cabin"], "economy")
        self.assertEqual(awards[1]["fare_type"], "market")
        self.assertEqual(awards[1]["mileage_cost"], 82000)
        self.assertEqual(awards[1]["segments"][0]["cabin"], "business")

    def test_ignores_return_component_for_one_way_search(self):
        payload = response()
        payload["NormalResults"]["product"][0]["tripComponent"].append({
            "position": 1,
            "ODoption": [{
                "startingMileage": 70000,
                "segment": [segment(origin="EWR", destination="FCO")],
            }],
        })

        self.assertEqual(len(parse_response(payload, QUERY)), 2)

    def test_rejects_route_mismatch_in_saved_response(self):
        payload = response()
        payload["NormalResults"]["product"][0]["tripComponent"][0]["ODoption"][0]["segment"][0]["destination"] = "YYZ"

        with self.assertRaisesRegex(ParseError, "destination does not match"):
            parse_response(payload, QUERY)

    def test_rejects_missing_expected_structure(self):
        with self.assertRaisesRegex(ParseError, "NormalResults.product"):
            parse_response({"NormalResults": {}}, QUERY)

    def test_returns_empty_list_when_no_options_exist(self):
        payload = {
            "NormalResults": {
                "product": [{
                    "name": "classic",
                    "tripComponent": [{"position": 0, "ODoption": []}],
                }],
            },
        }

        self.assertEqual(parse_response(payload, QUERY), [])

    def test_validates_query_fields(self):
        with self.assertRaisesRegex(ParseError, "three-letter"):
            validate_query("FC", "EWR", "2026-12-12", "economy")
        with self.assertRaisesRegex(ParseError, "YYYY-MM-DD"):
            validate_query("FCO", "EWR", "2026-2-12", "economy")

    def test_searches_saved_responses_by_route_date_range_and_cabin(self):
        first = response()
        second = copy.deepcopy(first)
        second_option = second["NormalResults"]["product"][0]["tripComponent"][0]["ODoption"][0]
        second_option["segment"][0]["departureDateTime"] = "2026-12-20T10:00:00"
        second_option["segment"][0]["arrivalDateTime"] = "2026-12-20T14:00:00"
        second_option["segment"][0]["flightNo"] = "AC 789"

        outside_range = copy.deepcopy(first)
        outside_option = outside_range["NormalResults"]["product"][0]["tripComponent"][0]["ODoption"][0]
        outside_option["segment"][0]["departureDateTime"] = "2027-01-02T10:00:00"

        with tempfile.TemporaryDirectory() as directory:
            response_dir = Path(directory)
            (response_dir / "dec-12.json").write_text(json.dumps(first), encoding="utf-8")
            (response_dir / "dec-20.json").write_text(json.dumps(second), encoding="utf-8")
            (response_dir / "jan-02.json").write_text(json.dumps(outside_range), encoding="utf-8")

            result = search_awards(
                "FCO", "EWR", "2026-12-12", "2026-12-20", "economy", response_dir
            )

        self.assertEqual(result["query"]["origin"], "FCO")
        self.assertEqual(
            [award["departure_date"] for award in result["awards"]],
            ["2026-12-12", "2026-12-20"],
        )
        self.assertTrue(all(award["cabin"] == "economy" for award in result["awards"]))

    def test_search_reports_missing_response_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing"
            with self.assertRaisesRegex(FileNotFoundError, "response directory does not exist"):
                search_awards("FCO", "EWR", "2026-12-12", "2026-12-20", "economy", missing)

    def test_search_rejects_reversed_date_range(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ParseError, "on or after"):
                search_awards("FCO", "EWR", "2026-12-20", "2026-12-12", "economy", directory)


if __name__ == "__main__":
    unittest.main()
