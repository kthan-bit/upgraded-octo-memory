# Local Award JSON Tools

These local scripts convert manually saved Air Canada availability responses into normalized JSON. They do not log in to Aeroplan, make network requests, or run Flightplan.

## Requirements

- Python 3.10+
- A response JSON file saved manually from an authorized source

The input must contain the `NormalResults.product` structure used by the Air Canada parser in Flightplan. No account credentials or browser session data should be included.

## Parse one response

```sh
python3 tools/parse_awards.py saved-response.json \
  --from FCO \
  --to EWR \
  --date 2026-12-12 \
  --cabin economy
```

Normalized JSON is written to standard output. To save it to a file:

```sh
python3 tools/parse_awards.py saved-response.json \
  --from FCO --to EWR --date 2026-12-12 --cabin economy \
  --output awards.json
```

Use `-` instead of the input path to read JSON from standard input. Input JSON is not stored by the script.

## Search a local response archive

Save response JSON files from searches you perform manually into `data/responses/`. Then search that local folder by route, date range, and cabin:

```sh
python3 -m tools.search_local_awards \
  --from FCO --to EWR \
  --start 2026-12-01 --end 2026-12-31 \
  --cabin economy \
  --output awards.json
```

The reusable function is `tools.search_local_awards.search_awards(airport_from, airport_to, date_start, date_end, cabin_class, response_dir=...)`. It reads only `*.json` files in the local response folder. The result is a JSON object with the normalized query and matching awards. It does not perform live searches; an empty `awards` list means no matching entries were found in the saved files.

## Output

The output includes the search parameters and normalized award options, including fixed/market fare type, mileage cost, and itinerary segments. It does not invent seat counts; the source response must provide them before they can be included.

## Tests

```sh
python3 -m unittest discover -s tests
```
