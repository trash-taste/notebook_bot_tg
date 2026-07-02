from __future__ import annotations

import argparse
from pathlib import Path

from packages.storage.import_jsonl import import_jsonl_files


def main() -> int:
    parser = argparse.ArgumentParser(description="Import legacy JSONL data into SQLite.")
    parser.add_argument("--db", default="data/notes.db", help="SQLite database path.")
    parser.add_argument("--notes", default="data/notes.jsonl", help="Legacy notes JSONL path.")
    parser.add_argument("--tasks", default="data/tasks.jsonl", help="Legacy tasks JSONL path.")
    args = parser.parse_args()

    counts = import_jsonl_files(
        db_path=Path(args.db),
        notes_jsonl=Path(args.notes),
        tasks_jsonl=Path(args.tasks),
    )
    print(
        "Imported: "
        f"captures={counts.captures}, "
        f"notes={counts.notes}, "
        f"tasks={counts.tasks}, "
        f"skipped_lines={counts.skipped_lines}"
    )
    print("JSONL files were not deleted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
