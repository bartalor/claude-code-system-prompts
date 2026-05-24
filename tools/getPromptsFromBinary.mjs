#!/usr/bin/env node
// Reads currently-embedded system prompts from a Claude Code installation
// and prints them as JSON to stdout. Driven by tools/applyPromptPatches.py
// so it can assert the binary still matches the upstream baseline before
// applying local prompt patches.
//
// Usage: getPromptsFromBinary.mjs <path-to-cli.js-or-native-binary>

import { tryDetectInstallation, getPromptsFromBinary } from 'tweakcc';

const path = process.argv[2];
if (!path) {
  console.error('Usage: getPromptsFromBinary.mjs <path>');
  process.exit(2);
}

const installation = await tryDetectInstallation({ path });
const prompts = await getPromptsFromBinary(installation);
process.stdout.write(
  JSON.stringify({ version: installation.version, prompts }, null, 2)
);
