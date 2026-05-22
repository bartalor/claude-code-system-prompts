#!/usr/bin/env python3
"""Stage the modified AskUserQuestion prompt into ~/.tweakcc/system-prompts,
run `tweakcc --apply`, and verify the disabled-message ended up in the
installed Claude Code binary.

Usage:
    applyAskUserQuestionDisable.py           # stage + apply + verify
    applyAskUserQuestionDisable.py --verify  # verify only (no staging, no apply)
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
PROMPT_FILE = REPO_DIR / "system-prompts" / "tool-description-askuserquestion.md"
TWEAKCC_DIR = Path.home() / ".tweakcc" / "system-prompts"
SENTINEL = b"DO NOT USE THIS TOOL. The user has disabled it."


def resolve_cc_target() -> Path:
    link = shutil.which("claude")
    if not link:
        sys.exit("claude not found on PATH")
    target = Path(link).resolve()
    if not target.exists():
        sys.exit(f"Could not resolve claude symlink: {link}")
    return target


def verify() -> bool:
    target = resolve_cc_target()
    print(f"Verifying patch in: {target}")
    if SENTINEL in target.read_bytes():
        print("OK: disabled-message present in installed Claude Code binary.")
        return True
    print(f"FAIL: disabled-message NOT found in {target}", file=sys.stderr)
    return False


def stage_and_apply() -> None:
    if not PROMPT_FILE.is_file():
        sys.exit(f"Prompt file missing: {PROMPT_FILE}")
    if SENTINEL.decode() not in PROMPT_FILE.read_text():
        sys.exit(
            f"Sentinel not found in {PROMPT_FILE} — refusing to apply.\n"
            f"Expected the file to contain: {SENTINEL.decode()}"
        )

    TWEAKCC_DIR.mkdir(parents=True, exist_ok=True)
    dest = TWEAKCC_DIR / PROMPT_FILE.name
    shutil.copy2(PROMPT_FILE, dest)
    print(f"Staged: {dest}")

    print("Running: npx tweakcc --apply")
    subprocess.run(["npx", "tweakcc", "--apply"], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify only; do not stage or apply.",
    )
    args = parser.parse_args()

    if args.verify:
        return 0 if verify() else 1

    stage_and_apply()
    return 0 if verify() else 1


if __name__ == "__main__":
    sys.exit(main())
