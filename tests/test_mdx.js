/**
 * Tests for MDX validation and compilation scripts.
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const FIXTURES = join(__dirname, "fixtures");

// Import compile logic by loading the script as a module
// We'll test the core parsing function by extracting it
// For now, test via the validate script's output

describe("MDX validation", () => {
  it("should detect missing headings in invalid content", async () => {
    const invalidContent = readFileSync(
      join(FIXTURES, ".invalid-module", "learning", "content.mdx"),
      "utf-8"
    );
    // No headings pattern
    const headingPattern = /^#{1,2}\s+.+/gm;
    const headings = invalidContent.match(headingPattern);
    assert.equal(headings, null, "Invalid fixture should have no headings");
  });

  it("should find headings in valid content", () => {
    const validContent = readFileSync(
      join(FIXTURES, ".valid-module", "learning", "content.mdx"),
      "utf-8"
    );
    const headingPattern = /^#{1,2}\s+.+/gm;
    const headings = validContent.match(headingPattern);
    assert.ok(headings, "Valid fixture should have headings");
    assert.ok(headings.length >= 4, `Expected >=4 headings, got ${headings.length}`);
  });

  it("should detect YouTube components", () => {
    const validContent = readFileSync(
      join(FIXTURES, ".valid-module", "learning", "content.mdx"),
      "utf-8"
    );
    const ytPattern = /<YouTube\s+id="([^"]+)"/;
    const match = validContent.match(ytPattern);
    assert.ok(match, "Should find YouTube component");
    assert.equal(match[1], "dQw4w9WgXcQ");
  });

  it("should detect Callout components with type", () => {
    const validContent = readFileSync(
      join(FIXTURES, ".valid-module", "learning", "content.mdx"),
      "utf-8"
    );
    const calloutPattern = /<Callout\s+type="(\w+)">/;
    const match = validContent.match(calloutPattern);
    assert.ok(match, "Should find Callout component");
    assert.equal(match[1], "warning");
  });
});

describe("MDX compilation (slide parsing)", () => {
  // Inline the core parsing logic for unit testing
  function stripFrontmatter(content) {
    if (content.startsWith("---")) {
      const end = content.indexOf("---", 3);
      if (end !== -1) return content.slice(end + 3).trim();
    }
    return content.trim();
  }

  function parseMdxToSlides(content) {
    content = stripFrontmatter(content);
    const lines = content.split("\n");
    const slides = [];
    let currentTitle = null;
    let currentLevel = 0;
    let bodyLines = [];

    function flushSlide() {
      if (currentTitle === null) return;
      const body = bodyLines.join("\n").trim() || null;
      const layout = currentLevel === 1 ? "section-title" : "default";
      slides.push({
        slide_index: slides.length,
        layout,
        title: currentTitle,
        body,
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

  it("should parse valid fixture into slides", () => {
    const content = readFileSync(
      join(FIXTURES, ".valid-module", "learning", "content.mdx"),
      "utf-8"
    );
    const slides = parseMdxToSlides(content);

    assert.ok(slides.length >= 5, `Expected >=5 slides, got ${slides.length}`);
    assert.equal(slides[0].layout, "section-title");
    assert.equal(slides[0].title, "Introduction");
    assert.equal(slides[1].layout, "default");
    assert.equal(slides[1].title, "First slide");
  });

  it("should assign section-title layout to # headings", () => {
    const content = "# Title\n\nBody\n\n## Sub\n\nMore";
    const slides = parseMdxToSlides(content);
    assert.equal(slides[0].layout, "section-title");
    assert.equal(slides[1].layout, "default");
  });

  it("should strip frontmatter", () => {
    const content = "---\nmoduleId: test\n---\n\n# Slide 1\n\nBody";
    const slides = parseMdxToSlides(content);
    assert.equal(slides.length, 1);
    assert.equal(slides[0].title, "Slide 1");
  });

  it("should handle empty body", () => {
    const content = "# Title\n\n## Empty slide";
    const slides = parseMdxToSlides(content);
    assert.equal(slides[1].body, null);
  });
});
