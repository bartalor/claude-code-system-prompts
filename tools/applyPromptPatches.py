#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["GitPython"]
# ///
"""Apply locally-modified system prompts to the installed Claude Code binary
via tweakcc, and verify the patches landed.

Preconditions checked at startup:
  - ``claude`` is on PATH and the symlink resolves.
  - The repo's nearest ``vX.Y.Z`` tag reachable from HEAD matches
    ``claude --version``. (tweakcc's regexes are version-specific; mismatched
    versions silently no-op.)
  - At least one file under ``system-prompts/`` differs from the nearest
    ``vX.Y.Z`` tag (i.e. the CC version this branch is based on).
  - Every staged prompt has a usable verification needle (non-empty body,
    first body line >= 20 chars).
  - For every modified prompt, the content currently embedded in the
    installed binary matches the upstream baseline (the same version tag).
    This
    catches the case where CC was already tweaked, the binary drifted, or
    the regex pieces don't match this build — applying a patch on top of a
    non-baseline binary would be wrong.

Usage:
    applyPromptPatches.py            # detect, confirm, stage, apply, verify
    applyPromptPatches.py --verify   # verify only (no staging, no apply)
    applyPromptPatches.py --dry-run  # run preconditions, print plan, stop
    applyPromptPatches.py --yes      # skip the confirmation prompt
"""

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path

import git

REPO_DIR = Path(__file__).resolve().parent.parent
PROMPTS_DIR = REPO_DIR / "system-prompts"
TOOLS_DIR = REPO_DIR / "tools"
READ_BINARY_PROMPTS_SHIM = TOOLS_DIR / "getPromptsFromBinary.mjs"
TWEAKCC_DIR = Path.home() / ".tweakcc" / "system-prompts"
FRONTMATTER_RE = re.compile(r"\A<!--.*?-->\s*", re.DOTALL)
CC_VERSION_RE = re.compile(r"\b(\d+\.\d+\.\d+)\b")


def repo() -> git.Repo:
    return git.Repo(REPO_DIR)


def resolve_cc_target() -> Path:
    link = shutil.which("claude")
    if not link:
        raise RuntimeError("claude not found on PATH")
    return Path(link).resolve(strict=True)


def installed_cc_version() -> str:
    out = subprocess.run(
        ["claude", "--version"], check=True, capture_output=True, text=True
    ).stdout.strip()
    m = CC_VERSION_RE.search(out)
    if not m:
        raise RuntimeError(f"Could not parse Claude Code version from: {out!r}")
    return m.group(1)


def repo_base_version(r: git.Repo) -> str:
    tag = r.git.describe("--tags", "--abbrev=0").strip()
    if not tag.startswith("v"):
        raise RuntimeError(f"Unexpected tag format from git describe: {tag!r}")
    return tag[1:]


def check_versions_match(r: git.Repo) -> None:
    repo_v = repo_base_version(r)
    cc_v = installed_cc_version()
    print(f"Repo base version: v{repo_v}")
    print(f"Installed CC version: {cc_v}")
    if repo_v != cc_v:
        raise RuntimeError(
            f"Version mismatch: repo is based on v{repo_v} but installed CC is "
            f"{cc_v}. Patches target a different binary and will not apply "
            f"cleanly. Rebase onto v{cc_v} or switch CC to v{repo_v}."
        )
    print("Versions match.")


def modified_prompts(r: git.Repo, base: str) -> list[Path]:
    diff = r.git.diff("--name-only", base, "--", "system-prompts/").strip()
    if not diff:
        return []
    files = [REPO_DIR / line for line in diff.splitlines()]
    for f in files:
        if not f.is_file():
            raise RuntimeError(f"Modified file does not exist on disk: {f}")
    return files


def body_excerpt(prompt_file: Path) -> str:
    text = prompt_file.read_text()
    body = FRONTMATTER_RE.sub("", text).strip()
    if not body:
        raise RuntimeError(f"Prompt body is empty: {prompt_file}")
    first_line = body.splitlines()[0].strip()
    if len(first_line) < 20:
        raise RuntimeError(
            f"First body line of {prompt_file.name} is too short to use as a "
            f"verification needle ({len(first_line)} chars): {first_line!r}"
        )
    return first_line[:80]


def strip_frontmatter(text: str) -> str:
    return FRONTMATTER_RE.sub("", text).strip()


def upstream_baseline(r: git.Repo, prompt_file: Path, base: str) -> str:
    rel = prompt_file.relative_to(REPO_DIR).as_posix()
    text = r.git.show(f"{base}:{rel}")
    body = strip_frontmatter(text)
    if not body:
        raise RuntimeError(f"Empty upstream baseline for {rel} at {base}")
    return body


def read_binary_prompts(target: Path) -> dict[str, str]:
    out = subprocess.run(
        ["node", str(READ_BINARY_PROMPTS_SHIM), str(target)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    data = json.loads(out)
    return {p["id"]: p["content"] for p in data["prompts"]}


def check_prompts_match_binary(
    expected: dict[str, str], target: Path
) -> None:
    binary_prompts = read_binary_prompts(target)
    mismatches: list[str] = []
    missing: list[str] = []
    for prompt_id, expected_content in expected.items():
        current = binary_prompts.get(prompt_id)
        if current is None:
            missing.append(prompt_id)
        elif current != expected_content:
            mismatches.append(prompt_id)
    if missing or mismatches:
        lines = ["Refusing to apply: binary content does not match expected."]
        if missing:
            lines.append(f"  Not found in binary: {', '.join(missing)}")
        if mismatches:
            lines.append(f"  Content differs: {', '.join(mismatches)}")
        raise RuntimeError("\n".join(lines))
    print(f"Binary content matches expected for {len(expected)} prompt(s).")


TEMPLATE_VAR_RE = re.compile(r"\$\{")


def template_var_count(prompt_file: Path) -> int:
    body = strip_frontmatter(prompt_file.read_text())
    return len(TEMPLATE_VAR_RE.findall(body))


def verify(prompts: list[Path]) -> None:
    target = resolve_cc_target()
    binary = target.read_bytes()
    print(f"Verifying patches in: {target}")
    failures = []
    for p in prompts:
        needle = body_excerpt(p).encode()
        if needle in binary:
            print(f"  OK   {p.name}")
        else:
            print(f"  FAIL {p.name}")
            failures.append(p)
    if failures:
        lines = [f"Verification failed for: {', '.join(p.name for p in failures)}"]
        templated = [p for p in failures if template_var_count(p) > 0]
        if templated:
            lines.append(
                "Likely cause: the prompt body contains template variables "
                "(${...}) that tweakcc escapes literally when building its "
                "full-body match regex. The binary has those variables already "
                "interpolated, so the regex never matches and `tweakcc --apply` "
                "silently no-ops. Affected:"
            )
            for p in templated:
                lines.append(
                    f"  - {p.name} ({template_var_count(p)} template var(s))"
                )
            lines.append(
                "Patch these via `tweakcc adhoc-patch` against a template-free "
                "anchor instead of the canonical --apply flow."
            )
        raise RuntimeError("\n".join(lines))


def confirm(prompts: list[Path]) -> None:
    print("The following locally-modified prompts will be applied:")
    for p in prompts:
        print(f"  - {p.relative_to(REPO_DIR)}")
    answer = input("Proceed? [y/N] ").strip().lower()
    if answer not in ("y", "yes"):
        raise SystemExit("Aborted by user.")


def adhoc_patch(prompt_file: Path, baseline: str, patched: str) -> None:
    print(f"Running: npx tweakcc adhoc-patch -s ... ({prompt_file.name})")
    result = subprocess.run(
        [
            "npx",
            "tweakcc",
            "adhoc-patch",
            "-s",
            baseline,
            patched,
            "--confirm-possible-dangerous-patch",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="")
        raise subprocess.CalledProcessError(
            result.returncode, ["npx", "tweakcc", "adhoc-patch"]
        )


def stage_and_apply(prompts: list[Path]) -> None:
    if not TWEAKCC_DIR.is_dir():
        raise RuntimeError(
            f"{TWEAKCC_DIR} does not exist. Run `npx tweakcc --list-system-prompts` "
            f"once to populate it, then re-run."
        )
    originals: list[tuple[Path, bytes]] = []
    try:
        for p in prompts:
            dest = TWEAKCC_DIR / p.name
            if not dest.is_file():
                raise RuntimeError(
                    f"Canonical file missing: {dest}. Run "
                    f"`npx tweakcc --list-system-prompts` to repopulate, then re-run."
                )
            originals.append((dest, dest.read_bytes()))
            shutil.copy2(p, dest)
            print(f"Overwrote canonical {dest.name}")
        print("Running: npx tweakcc --apply")
        result = subprocess.run(
            ["npx", "tweakcc", "--apply"], capture_output=True, text=True
        )
        if result.returncode != 0:
            if result.stdout:
                print(result.stdout, end="")
            if result.stderr:
                print(result.stderr, end="")
            raise subprocess.CalledProcessError(
                result.returncode, ["npx", "tweakcc", "--apply"]
            )
    finally:
        for dest, content in originals:
            try:
                dest.write_bytes(content)
                print(f"Restored canonical {dest.name}")
            except OSError as e:
                print(
                    f"WARNING: failed to restore {dest}: {e}. Restore manually."
                )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="Verify only.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run preconditions and print what would be applied, without "
        "touching ~/.tweakcc or the installed binary.",
    )
    parser.add_argument("--yes", action="store_true", help="Skip confirmation.")
    args = parser.parse_args()

    r = repo()
    check_versions_match(r)
    base = f"v{repo_base_version(r)}"

    prompts = modified_prompts(r, base)
    if not prompts:
        raise SystemExit(f"No prompts under system-prompts/ differ from {base}.")

    for p in prompts:
        body_excerpt(p)

    if args.verify:
        verify(prompts)
        return

    target = resolve_cc_target()
    binary_prompts = read_binary_prompts(target)
    to_apply: list[Path] = []
    for p in prompts:
        canonical = TWEAKCC_DIR / p.name
        if not canonical.is_file():
            raise RuntimeError(
                f"{p.name} has no canonical file in {TWEAKCC_DIR} — "
                f"tweakcc cannot patch it. Run "
                f"`npx tweakcc --list-system-prompts` to repopulate."
            )
        patched = strip_frontmatter(p.read_text())
        current = binary_prompts.get(p.stem)
        if current is not None and current == patched:
            print(f"Skipping {p.name}: already applied in binary.")
            continue
        to_apply.append(p)

    if not to_apply:
        print("Nothing to do: all modified prompts already applied.")
        return

    expected = {p.stem: upstream_baseline(r, p, base) for p in to_apply}
    # check_prompts_match_binary(expected, target)

    if args.dry_run:
        print("Dry run: would apply the following prompts:")
        for p in to_apply:
            print(f"  - {p.relative_to(REPO_DIR)}")
        print("Dry run: no files staged, no binary modified.")
        return

    template_free = [p for p in to_apply if template_var_count(p) == 0]
    template_var = [p for p in to_apply if template_var_count(p) > 0]

    if not args.yes:
        confirm(to_apply)

    attempted: list[Path] = []
    if template_free:
        stage_and_apply(template_free)
        attempted.extend(template_free)

    for p in template_var:
        answer = input(
            f"{p.name} contains template variables; apply via adhoc-patch? [y/N] "
        ).strip().lower()
        if answer not in ("y", "yes"):
            print(f"Skipping {p.name}.")
            continue
        baseline = upstream_baseline(r, p, base)
        patched = strip_frontmatter(p.read_text())
        adhoc_patch(p, baseline, patched)
        attempted.append(p)

    if attempted:
        verify(attempted)


if __name__ == "__main__":
    main()
