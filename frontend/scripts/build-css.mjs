import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const frontendDir = resolve(scriptDir, "..");
const result = spawnSync("npx", ["@tailwindcss/cli", "-i", "./src/css/input.css", "-o", "../static/css/tailwind-build.css", "--minify"], {
  cwd: frontendDir,
  stdio: "inherit",
});

if (result.status !== 0) process.exit(result.status ?? 1);

const output = resolve(frontendDir, "../static/css/tailwind-build.css");
const header = `/* LLMWikiNG – Copyright (C) 2026 ZeroDot1\n * Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).\n * SPDX-License-Identifier: AGPL-3.0-or-later\n */\n`;
let css = readFileSync(output, "utf8").replace(/^\/\* LLMWikiNG[\s\S]*?\*\/\n/, "");
writeFileSync(output, header + css.trimEnd() + "\n", "utf8");
