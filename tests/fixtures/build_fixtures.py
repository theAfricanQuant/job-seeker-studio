"""Compile the fixture CVs under tests/fixtures and report what the reader makes of them."""

from __future__ import annotations

import importlib.util
import pathlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_app():
    spec = importlib.util.spec_from_file_location("field_notes_fixture", ROOT / "app.py")
    assert spec and spec.loader
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    return app


def main() -> None:
    app = load_app()
    for source in sorted((ROOT / "tests" / "fixtures").glob("*.typ")):
        output = source.with_suffix(".pdf")
        ok, error = app.compile_typst(source, output)
        print(f"{source.name}: compiled={ok} {error}".rstrip())
        if not ok:
            continue
        raw = app.extract_text(output)
        print("  zero-width stripped by the reader:", "\u200b" not in raw)
        profile = app.profile_from_text(raw, output.name, "fixture-token")
        print("  name     ", repr(profile["name"]))
        print("  location ", repr(profile["location"]))
        print("  headline ", repr(profile["headline"]))
        print("  languages", profile["languages"])
        for record in profile["experiences"]:
            print("  exp      ", repr(record["title"]), "|", repr(record["subtitle"]), "|", record["dates"], "|", repr(record["location"]), "| bullets", len(record["bullets"]))
        for record in profile["education"]:
            print("  edu      ", repr(record["title"]), "|", repr(record["subtitle"]), "|", record["dates"], "|", repr(record["location"]))


if __name__ == "__main__":
    main()