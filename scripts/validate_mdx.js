/**
 * MDX content validator.
 *
 * Parses content.mdx files and validates:
 * - Valid MDX syntax (parseable)
 * - At least one slide (heading) exists
 * - Known component usage (<Callout>, <YouTube>, <Figure>)
 * - YouTube/Figure component props are valid
 * - No empty modules
 *
 * Usage:
 *   node scripts/validate_mdx.js <path-to-content.mdx>
 *   node scripts/validate_mdx.js <path-to-modules-dir>
 *
 * Exit codes:
 *   0 — valid
 *   1 — validation errors found
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { basename, join, resolve } from "node:path";
import { compile } from "@mdx-js/mdx";

// Known MDX components that are valid in content
const KNOWN_COMPONENTS = new Set(["Callout", "YouTube", "Figure", "Video"]);
const VALID_CALLOUT_TYPES = new Set(["info", "warning", "success"]);

/**
 * @typedef {Object} ValidationError
 * @property {string} file
 * @property {number|null} line
 * @property {string} message
 */

/**
 * Validate a single content.mdx file.
 * @param {string} filePath
 * @returns {Promise<ValidationError[]>}
 */
async function validateMdxFile(filePath) {
  const errors = /** @type {ValidationError[]} */ ([]);
  const relPath = filePath;

  let content;
  try {
    content = readFileSync(filePath, "utf-8");
  } catch {
    errors.push({ file: relPath, line: null, message: "Cannot read file" });
    return errors;
  }

  if (content.trim().length === 0) {
    errors.push({ file: relPath, line: null, message: "File is empty" });
    return errors;
  }

  // Check MDX is parseable
  try {
    await compile(content, { remarkPlugins: [], rehypePlugins: [] });
  } catch (/** @type {any} */ e) {
    errors.push({
      file: relPath,
      line: e.line ?? null,
      message: `MDX parse error: ${e.message}`,
    });
    return errors; // Cannot continue if unparseable
  }

  // Check for at least one heading (slide)
  const headingPattern = /^#{1,2}\s+.+/gm;
  const headings = content.match(headingPattern);
  if (!headings || headings.length === 0) {
    errors.push({
      file: relPath,
      line: null,
      message: "No headings found — content must have at least one slide (# or ## heading)",
    });
  }

  // Validate component usage
  const componentPattern = /<(\w+)(\s[^>]*)?\/?>/g;
  const lines = content.split("\n");

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    let match;
    componentPattern.lastIndex = 0;

    while ((match = componentPattern.exec(line)) !== null) {
      const componentName = match[1];

      // Skip standard HTML elements (lowercase)
      if (componentName[0] === componentName[0].toLowerCase()) continue;

      if (!KNOWN_COMPONENTS.has(componentName)) {
        errors.push({
          file: relPath,
          line: i + 1,
          message: `Unknown component <${componentName}>. Known: ${[...KNOWN_COMPONENTS].join(", ")}`,
        });
      }

      // Validate Callout type prop
      if (componentName === "Callout") {
        const typeMatch = match[0].match(/type="(\w+)"/);
        if (!typeMatch) {
          errors.push({
            file: relPath,
            line: i + 1,
            message: '<Callout> must have a type prop (info, warning, or success)',
          });
        } else if (!VALID_CALLOUT_TYPES.has(typeMatch[1])) {
          errors.push({
            file: relPath,
            line: i + 1,
            message: `<Callout type="${typeMatch[1]}"> — invalid type. Must be: ${[...VALID_CALLOUT_TYPES].join(", ")}`,
          });
        }
      }

      // Validate YouTube component
      if (componentName === "YouTube") {
        const idMatch = match[0].match(/id="([^"]+)"/);
        if (!idMatch) {
          errors.push({
            file: relPath,
            line: i + 1,
            message: '<YouTube> must have an id prop',
          });
        }
      }

      // Validate Video component (V2)
      if (componentName === "Video") {
        const hasYoutubeId = /youtubeId="[^"]+"/.test(match[0]);
        const hasSrc = /src="[^"]+"/.test(match[0]);
        if (!hasYoutubeId && !hasSrc) {
          errors.push({
            file: relPath,
            line: i + 1,
            message: '<Video> must have either youtubeId or src prop',
          });
        }
        if (hasYoutubeId && hasSrc) {
          errors.push({
            file: relPath,
            line: i + 1,
            message: '<Video> must have exactly one of youtubeId or src, not both',
          });
        }
      }

      // Validate Figure component
      if (componentName === "Figure") {
        const hasSrc = /src="[^"]+"/.test(match[0]);
        const hasAlt = /alt="[^"]+"/.test(match[0]);
        if (!hasSrc) {
          errors.push({
            file: relPath,
            line: i + 1,
            message: '<Figure> must have a src prop',
          });
        }
        if (!hasAlt) {
          errors.push({
            file: relPath,
            line: i + 1,
            message: '<Figure> must have an alt prop (accessibility)',
          });
        }
      }
    }
  }

  return errors;
}

/**
 * Find all content.mdx files in a modules directory.
 * @param {string} modulesDir
 * @returns {string[]}
 */
function findMdxFiles(modulesDir) {
  const files = [];
  const entries = readdirSync(modulesDir);

  for (const entry of entries) {
    if (entry.startsWith(".")) continue;
    const modulePath = join(modulesDir, entry);
    if (!statSync(modulePath).isDirectory()) continue;

    const contentPath = join(modulePath, "learning", "content.mdx");
    try {
      statSync(contentPath);
      files.push(contentPath);
    } catch {
      // No learning content — that's fine (assessment-only module)
    }
  }

  return files;
}

/**
 * Main entry point.
 */
async function main() {
  const args = process.argv.slice(2);

  if (args.length === 0) {
    console.error("Usage: node scripts/validate_mdx.js <path>");
    console.error("  <path> can be a content.mdx file or a modules/ directory");
    process.exit(1);
  }

  const target = resolve(args[0]);
  let files;

  const stat = statSync(target);
  if (stat.isFile()) {
    files = [target];
  } else if (stat.isDirectory()) {
    // Check if this is a modules/ dir or a single module dir
    const contentPath = join(target, "learning", "content.mdx");
    try {
      statSync(contentPath);
      files = [contentPath];
    } catch {
      files = findMdxFiles(target);
    }
  } else {
    console.error(`Not a file or directory: ${target}`);
    process.exit(1);
  }

  if (files.length === 0) {
    console.log("No content.mdx files found.");
    process.exit(0);
  }

  let totalErrors = 0;
  for (const file of files) {
    const errors = await validateMdxFile(file);
    if (errors.length > 0) {
      totalErrors += errors.length;
      for (const err of errors) {
        const loc = err.line ? `:${err.line}` : "";
        console.error(`ERROR ${err.file}${loc}: ${err.message}`);
      }
    }
  }

  console.log(
    `\nValidated ${files.length} file(s). ${totalErrors === 0 ? "All valid." : `${totalErrors} error(s) found.`}`
  );
  process.exit(totalErrors === 0 ? 0 : 1);
}

main();
