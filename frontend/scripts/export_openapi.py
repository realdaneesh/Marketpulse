"""Export the actual FastAPI contract without opening or changing any database."""

import argparse
import json
from pathlib import Path

from marketpulse.api.app import create_app

parser = argparse.ArgumentParser()
parser.add_argument("--check", action="store_true")
args = parser.parse_args()
destination = Path(__file__).resolve().parents[1] / "openapi.json"
content = json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"
if args.check:
    if destination.read_text(encoding="utf-8") != content:
        raise SystemExit("OpenAPI snapshot differs; regenerate the snapshot and TypeScript types.")
    print("OpenAPI snapshot matches the backend.")
else:
    destination.write_text(content, encoding="utf-8")
    print("Exported OpenAPI contract.")
