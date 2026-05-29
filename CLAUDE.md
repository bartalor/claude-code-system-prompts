# Claude Code System Prompts

## What this repository is

System prompts extracted via script from the Claude Code npm package's compiled JavaScript source. Maintained by [Piebald AI](https://piebald.ai/), not by Anthropic.

See the [Extraction section in README.md](./README.md#extraction) for details on the extraction method.

## What Claude Code is

Claude Code is Anthropic's CLI tool for agentic coding. It is distributed as a compiled npm package (`@anthropic-ai/claude-code`). Source code is not publicly available. The [anthropics/claude-code](https://github.com/anthropics/claude-code) GitHub repository contains issues and releases only.

## How to use these files

- **Reference:** Understand what prompts Claude Code uses and how they change across versions
- **Local patching (tweakcc):** Use [tweakcc](https://github.com/Piebald-AI/tweakcc) to customize individual prompt pieces in your local Claude Code installation
- **Local patching (this repo's toolchain):** On branches that carry edits, [tools/applyPromptPatches.py](./tools/applyPromptPatches.py) applies the locally-modified `system-prompts/` files to the installed Claude Code binary via tweakcc and verifies the patches landed
- **Feature requests:** For changes to Claude Code's prompts, file issues at [anthropics/claude-code/issues](https://github.com/anthropics/claude-code/issues)

## Patching the installed binary

This repo is no longer reference-only. The `tools/` toolchain bridges the `system-prompts/` markdown back into the installed Claude Code binary:

- [tools/applyPromptPatches.py](./tools/applyPromptPatches.py) — detects which prompts differ from the version baseline, then applies and verifies them against the installed binary via tweakcc. Supports `--verify`, `--dry-run`, and `--yes`.
- [tools/getPromptsFromBinary.mjs](./tools/getPromptsFromBinary.mjs) — extracts the prompts currently embedded in the installed binary.
- tweakcc's canonical dir (`~/.tweakcc/system-prompts`) is treated as the source-of-truth in the apply flow.
- The apply flow is version-specific: tweakcc's regexes only match the Claude Code version the branch is based on (the nearest `vX.Y.Z` tag), so a version mismatch silently no-ops.

## For AI agents working with this repository

- On `main`, the `system-prompts/` files are **extracted reference material** — editing them does not change Claude Code's behavior.
- On working branches, the `tools/` patch applier *can* push these edits into the installed binary, so changes here are no longer inert.
- The `system-prompts/` directory contains markdown files with YAML frontmatter noting the Claude Code version and template variables
- Template variables like `${BASH_TOOL_NAME}` are interpolated at runtime by Claude Code — they appear as literal strings in these files
- The [CHANGELOG.md](./CHANGELOG.md) tracks prompt changes across Claude Code versions
