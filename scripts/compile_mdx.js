/**
 * MDX compiler — converts content.mdx into compiled.json.
 *
 * Parses MDX using heading-based slide splitting (same logic as the
 * backend's mdx_parser.py) and outputs a JSON array of slide objects
 * for the deploy pipeline to sync to the API.
 *
 * Usage:
 *   node scripts/compile_mdx.js <path-to-content.mdx> [output-path]
 *   node scripts/compile_mdx.js <path-to-modules-dir>
 *
 * When given a modules directory, outputs compiled.json next to each
 * content.mdx file.
 */

import { readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

/**
 * @typedef {Object} CompiledSlide
 * @property {number} slide_index
 * @property {string} layout
 * @property {string} title
 * @property {string|null} body
 * @property {string|null} callout_type
 * @property {string|null} callout_body
 * @property {string|null} youtube_id
 * @property {number|null} duration_seconds
 */

/**
 * Strip YAML frontmatter from MDX content.
 * @param {string} content
 * @returns {string}
 */
function stripFrontmatter(content) {
  if (content.startsWith("---")) {
    const end = content.indexOf("---", 3);
    if (end !== -1) {
      return content.slice(end + 3).trim();
    }
  }
  return content.trim();
}

/**
 * Extract <Callout> component from body text.
 * @param {string} body
 * @returns {{ remaining: string, calloutType: string|null, calloutBody: string|null }}
 */
function extractCallout(body) {
  const pattern = /<Callout\s+type="(\w+)">\s*([\s\S]*?)\s*<\/Callout>/;
  const match = body.match(pattern);
  if (!match) {
    return { remaining: body, calloutType: null, calloutBody: null };
  }
  const remaining = (body.slice(0, match.index) + body.slice(match.index + match[0].length)).trim();
  return {
    remaining,
    calloutType: match[1],
    calloutBody: match[2].trim(),
  };
}

/**
 * Extract <YouTube> component from body text.
 * @param {string} body
 * @returns {{ remaining: string, youtubeId: string|null, durationSeconds: number|null }}
 */
function extractYouTube(body) {
  const pattern = /<YouTube\s+id="([^"]+)"(?:\s+duration=\{(\d+)\})?\s*\/>/;
  const match = body.match(pattern);
  if (!match) {
    return { remaining: body, youtubeId: null, durationSeconds: null };
  }
  const remaining = (body.slice(0, match.index) + body.slice(match.index + match[0].length)).trim();
  return {
    remaining,
    youtubeId: match[1],
    durationSeconds: match[2] ? parseInt(match[2], 10) : null,
  };
}

/**
 * Parse MDX content into slide array.
 * Mirrors backend/app/features/teaching/mdx_parser.py logic.
 * @param {string} content
 * @returns {CompiledSlide[]}
 */
function parseMdxToSlides(content) {
  content = stripFrontmatter(content);
  const lines = content.split("\n");
  const slides = /** @type {CompiledSlide[]} */ ([]);

  let currentTitle = /** @type {string|null} */ (null);
  let currentLevel = 0;
  let bodyLines = /** @type {string[]} */ ([]);

  function flushSlide() {
    if (currentTitle === null) return;

    let body = bodyLines.join("\n").trim() || null;
    let layout = currentLevel === 1 ? "section-title" : "default";
    let calloutType = null;
    let calloutBody = null;
    let youtubeId = null;
    let durationSeconds = null;

    if (body) {
      const calloutResult = extractCallout(body);
      body = calloutResult.remaining;
      calloutType = calloutResult.calloutType;
      calloutBody = calloutResult.calloutBody;

      const ytResult = extractYouTube(body || "");
      if (ytResult.youtubeId) {
        layout = "video-slide";
        body = ytResult.remaining || null;
        youtubeId = ytResult.youtubeId;
        durationSeconds = ytResult.durationSeconds;
      }

      if (!body) body = null;
    }

    slides.push({
      slide_index: slides.length,
      layout,
      title: currentTitle,
      body,
      callout_type: calloutType,
      callout_body: calloutBody,
      youtube_id: youtubeId,
      duration_seconds: durationSeconds,
    });

    currentTitle = null;
    bodyLines = [];
    currentLevel = 0;
  }

  for (const line of lines) {
    const h1Match = line.match(/^#\s+(.+)$/);
    const h2Match = line.match(/^##\s+(.+)$/);

    if (h1Match) {
      flushSlide();
      currentTitle = h1Match[1].trim();
      currentLevel = 1;
    } else if (h2Match) {
      flushSlide();
      currentTitle = h2Match[1].trim();
      currentLevel = 2;
    } else if (currentTitle !== null) {
      bodyLines.push(line);
    }
  }

  flushSlide();
  return slides;
}

/**
 * Compile a single content.mdx file.
 * @param {string} inputPath
 * @param {string} [outputPath]
 */
function compileFile(inputPath, outputPath) {
  const content = readFileSync(inputPath, "utf-8");
  const slides = parseMdxToSlides(content);
  const out = outputPath || join(dirname(inputPath), "compiled.json");
  writeFileSync(out, JSON.stringify(slides, null, 2) + "\n");
  console.log(`  ${inputPath} → ${out} (${slides.length} slides)`);
}

/**
 * Find and compile all content.mdx files in a modules directory.
 * @param {string} modulesDir
 */
function compileModulesDir(modulesDir) {
  const entries = readdirSync(modulesDir);
  let count = 0;

  for (const entry of entries) {
    if (entry.startsWith(".")) continue;
    const modulePath = join(modulesDir, entry);
    if (!statSync(modulePath).isDirectory()) continue;

    const contentPath = join(modulePath, "learning", "content.mdx");
    try {
      statSync(contentPath);
      compileFile(contentPath);
      count++;
    } catch {
      // No learning content — skip
    }
  }

  console.log(`\nCompiled ${count} module(s).`);
}

/**
 * Main entry point.
 */
function main() {
  const args = process.argv.slice(2);

  if (args.length === 0) {
    console.error("Usage: node scripts/compile_mdx.js <path> [output]");
    console.error("  <path> can be a content.mdx file or a modules/ directory");
    process.exit(1);
  }

  const target = resolve(args[0]);
  const stat = statSync(target);

  if (stat.isFile()) {
    compileFile(target, args[1] ? resolve(args[1]) : undefined);
  } else if (stat.isDirectory()) {
    // Check if this is a single module with learning/content.mdx
    const contentPath = join(target, "learning", "content.mdx");
    try {
      statSync(contentPath);
      compileFile(contentPath);
    } catch {
      compileModulesDir(target);
    }
  } else {
    console.error(`Not a file or directory: ${target}`);
    process.exit(1);
  }
}

main();
