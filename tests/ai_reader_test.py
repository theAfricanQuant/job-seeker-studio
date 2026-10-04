"""Compare the three readers on real CVs and on layouts the rules were not tuned on.

    python3 tests/ai_reader_test.py [path ...]

Default: the two real CVs, every sample in template_samples/pdfs, and every fixture in
tests/fixtures/hard. Each input is read three ways — the rules, the model labelling every
unit, and the hybrid — and the three readings are printed side by side.
"""
from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))          # before app.py loads, so its AI layer can import
spec = importlib.util.spec_from_file_location("field_notes_app", ROOT / "app.py")
app = importlib.util.module_from_spec(spec)
sys.modules["field_notes_app"] = app
spec.loader.exec_module(app)
import ai_reader  # noqa: E402

REAL = [
    Path("/root/.hermes/cache/documents/doc_bd7d94762df3_Core_CV.pdf"),
    Path("/root/.hermes/cache/documents/doc_a41cbe54d716_CV__Ene Macharm_April 2023.pdf"),
]
RESULTS: list[dict] = []


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.suffix == ".txt" else app.extract_text(path)


def line(label: str, fields: dict, extra: str = "") -> str:
    roles = fields.get("experiences", [])
    body = f"  {label:<7} name={fields.get('name')!r:<30} roles={len(roles):<2} edu={len(fields.get('education', [])):<2} " \
           f"lang={len(fields.get('languages', [])):<2} skills={len(fields.get('skills', [])):<3}{extra}"
    for role in roles:
        body += f"\n          - {role['dates'][:20]:<20} {role['title'][:46]:<46} @ {role['subtitle'][:34]:<34} b={len(role['bullets'])}"
    return body


def run(path: Path) -> None:
    text = read_text(path)
    lines = app.cv_lines(text)
    print(f"\n=== {path.name}  ({len(lines)} lines)")
    row = {"file": path.name}

    rules = app.rules_fields(text)
    row["rules_roles"], row["rules_name"] = len(rules["experiences"]), rules["name"]
    print(line("rules", rules))

    before = ai_reader.usage()
    try:
        labelled = ai_reader.read_profile(lines, language_formatter=app.language_entry)
        labelled["name"] = app.name_candidate(ai_reader.clean_name_line(labelled["name_line"]))
        row["labels_roles"], row["labels_name"] = len(labelled["experiences"]), labelled["name"]
        spent = ai_reader.usage()["input_tokens"] - before["input_tokens"]
        calls = ai_reader.usage()["requests"] - before["requests"]
        print(line("labels", labelled, f"  [{calls} q, {spent} tok, ${spent * 0.042 / 1e6:.5f}]"))
    except ai_reader.Unavailable as error:
        row["labels_roles"], row["labels_name"] = -1, ""
        print(f"  labels  unavailable: {error}")

    before = ai_reader.usage()
    started = time.time()
    hybrid, notes = app.ai_hybrid_profile(text, path.name, f"ai-test-{abs(hash(path.name))}")
    row["hybrid_roles"], row["hybrid_name"] = len(hybrid["experiences"]), hybrid["name"]
    spent = ai_reader.usage()["input_tokens"] - before["input_tokens"]
    calls = ai_reader.usage()["requests"] - before["requests"]
    print(line("hybrid", hybrid, f"  [{calls} q, {spent} tok, ${spent * 0.042 / 1e6:.5f}, {time.time() - started:.1f}s] {notes}"))
    RESULTS.append(row)


def summary() -> None:
    print(f"\n\n{'CV':<36} {'roles r/l/h':>13} {'name r/l/h':>13}  verdict")
    agree = 0
    for row in RESULTS:
        same = row["rules_roles"] == row["hybrid_roles"] and row["rules_name"] == row["hybrid_name"]
        agree += same
        print(f"{row['file'][:35]:<36} "
              f"{row['rules_roles']:>4}/{row['labels_roles']:<4}/{row['hybrid_roles']:<3} "
              f"{'ok' if row['rules_name'] == row['labels_name'] else 'no':>4}/"
              f"{'ok' if row['rules_name'] == row['hybrid_name'] else 'no':<4}/"
              f"{'ok' if row['hybrid_name'] else 'no':<3} {'same' if same else 'DIFFERS'}")
    print(f"\n{agree} of {len(RESULTS)} identical between rules and hybrid")
    print(f"total tokens: {ai_reader.usage()}")


def main() -> None:
    args = [Path(p) for p in sys.argv[1:]]
    targets = args or (REAL
                       + sorted((ROOT / "template_samples" / "pdfs").glob("*.pdf"))
                       + sorted((ROOT / "tests" / "fixtures" / "hard").glob("*.txt")))
    for path in targets:
        if path.exists():
            run(path)
    summary()


if __name__ == "__main__":
    main()