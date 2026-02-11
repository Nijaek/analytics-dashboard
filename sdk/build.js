/**
 * Simple build script to minify the tracker SDK.
 * Usage: node build.js
 * Output: dist/sdk.js and dist/sdk.min.js
 */
const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(path.join(__dirname, "src", "tracker.js"), "utf8");

// Create dist directory
const distDir = path.join(__dirname, "dist");
if (!fs.existsSync(distDir)) {
  fs.mkdirSync(distDir, { recursive: true });
}

// Copy unminified
fs.writeFileSync(path.join(distDir, "sdk.js"), src);

// Simple minification (strip comments, collapse whitespace)
let minified = src
  .replace(/\/\*[\s\S]*?\*\//g, "")    // block comments
  .replace(/\/\/.*$/gm, "")             // line comments
  .replace(/\n\s*\n/g, "\n")            // blank lines
  .replace(/^\s+/gm, "")               // leading whitespace
  .trim();

fs.writeFileSync(path.join(distDir, "sdk.min.js"), minified);

const size = Buffer.byteLength(minified, "utf8");
console.log(`SDK built: ${size} bytes (${(size / 1024).toFixed(1)}KB)`);
