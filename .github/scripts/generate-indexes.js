#!/usr/bin/env node
/**
 * generate-indexes.js
 *
 * Generates:
 *   book/BOOK-INDEX.md — chapter list with section headings and line numbers
 *   src/ADR-INDEX.md   — all ADR.md files with role summaries
 *
 * Run from the repository root (where book/ and src/ live).
 * An explicit --outer-repo <path> override is available if needed.
 */

const fs   = require('fs');
const path = require('path');

const args = process.argv.slice(2);
const outerRepoFlag = args.indexOf('--outer-repo');
const outerRepo = outerRepoFlag !== -1
  ? path.resolve(args[outerRepoFlag + 1])
  : process.cwd();

// --book-only / --adr-only allow callers to generate just one index.
// Without either flag both indexes are generated (backward-compatible).
const bookOnly = args.includes('--generate-book-index');
const adrOnly  = args.includes('--generate-adr-index');

const bookDir  = path.join(outerRepo, 'book');
const srcDir   = path.join(outerRepo, 'src');
const today    = new Date().toISOString().slice(0, 10);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function toAnchor(heading) {
  return heading
    .toLowerCase()
    .replace(/[`'"]/g, '')
    .replace(/[^a-z0-9\s-]/g, '')
    .trim()
    .replace(/\s+/g, '-');
}

/** Extract first non-empty paragraph after a ## heading */
function extractRoleSummary(lines, headingIndex) {
  let i = headingIndex + 1;
  while (i < lines.length && lines[i].trim() === '') i++;
  const paragraphLines = [];
  while (i < lines.length && lines[i].trim() !== '' && !lines[i].startsWith('#')) {
    paragraphLines.push(lines[i].trim());
    i++;
  }
  const text = paragraphLines.join(' ');
  // Return first sentence (up to first full stop followed by space or end)
  const match = text.match(/^(.+?[.!?])(?:\s|$)/);
  return match ? match[1] : text.slice(0, 120) + (text.length > 120 ? '…' : '');
}

// ---------------------------------------------------------------------------
// Book index
// ---------------------------------------------------------------------------

function generateBookIndex() {
  if (!fs.existsSync(bookDir)) {
    console.warn(`⚠ Book directory not found at ${bookDir} — skipping book index`);
    return false;
  }

  const chapterFiles = fs.readdirSync(bookDir)
    .filter(f => /^\d{2}-/.test(f) && f.endsWith('.md'))
    .sort();

  if (chapterFiles.length === 0) {
    console.warn(`⚠ No numbered chapter files found in ${bookDir} — skipping book index`);
    return false;
  }

  const lines = [
    '# Book Index',
    '',
    `${chapterFiles.length} chapters · generated ${today}`,
    '',
    'Each chapter file contains detailed sections with source citations.',
    '',
    '---',
    '',
    '## Chapters',
    '',
  ];

  const chapterDetails = [];

  for (const file of chapterFiles) {
    const content  = fs.readFileSync(path.join(bookDir, file), 'utf8');
    const fileLines = content.split('\n');

    // Extract h1 title
    const h1Line = fileLines.find(l => l.startsWith('# '));
    const title  = h1Line ? h1Line.replace(/^# /, '').trim() : file;

    // Extract h2 sections (skip lines that are actually code/comment artifacts)
    const sections = [];
    fileLines.forEach((l, idx) => {
      if (/^## /.test(l)) {
        sections.push({ name: l.replace(/^## /, '').trim(), line: idx + 1 });
      }
    });

    lines.push(`- [${title}](${file}) — ${sections.length} sections`);
    chapterDetails.push({ file, title, sections });
  }

  lines.push('', '---', '');

  for (const { file, title, sections } of chapterDetails) {
    lines.push(`## ${title}`, '');
    lines.push(`→ [\`${file}\`](${file})`, '');
    lines.push('| Line | Section |', '|---:|---|');
    for (const s of sections) {
      const anchor = toAnchor(s.name);
      lines.push(`| ${s.line} | [${s.name}](${file}#${anchor}) |`);
    }
    lines.push('');
  }

  const out = path.join(bookDir, 'BOOK-INDEX.md');
  fs.writeFileSync(out, lines.join('\n'));
  console.log(`✓ Book index written → ${out}  (${chapterDetails.length} chapters)`);
  return true;
}

// ---------------------------------------------------------------------------
// ADR index
// ---------------------------------------------------------------------------

function findAdrFiles(dir, base) {
  const results = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    const rel  = path.join(base, entry.name);
    if (entry.isDirectory()) {
      results.push(...findAdrFiles(full, rel));
    } else if (entry.name === 'ADR.md') {
      results.push({ full, rel });
    }
  }
  return results.sort((a, b) => a.rel.localeCompare(b.rel));
}

function generateAdrIndex() {
  if (!fs.existsSync(srcDir)) {
    console.warn(`⚠ src directory not found at ${srcDir} — skipping ADR index`);
    return false;
  }

  const adrs = findAdrFiles(srcDir, '');

  if (adrs.length === 0) {
    console.warn(`⚠ No ADR.md files found under ${srcDir} — skipping ADR index`);
    return false;
  }

  const lines = [
    '# ADR Index',
    '',
    `${adrs.length} Architecture Decision Records · generated ${today}`,
    '',
    'Each `ADR.md` describes the role, key files, public interface, dependencies,',
    'design rationale, constraints, and observability of one directory.',
    '',
    '---',
    '',
    '| # | Path | Role |',
    '|---:|---|---|',
  ];

  for (let i = 0; i < adrs.length; i++) {
    const { full, rel } = adrs[i];
    const content    = fs.readFileSync(full, 'utf8');
    const fileLines  = content.split('\n');

    // Title from h1
    const h1 = fileLines.find(l => l.startsWith('# '));
    const title = h1 ? h1.replace(/^# /, '').trim() : rel;

    // Role: first paragraph after ## Role
    const roleIdx = fileLines.findIndex(l => /^## Role/.test(l));
    const role = roleIdx !== -1 ? extractRoleSummary(fileLines, roleIdx) : '—';

    // Relative link from src/ADR-INDEX.md — rel already starts without leading /
    const relPath = rel.startsWith(path.sep) ? rel.slice(1) : rel;
    lines.push(`| ${i + 1} | [${relPath}](${relPath}) | ${role} |`);
  }

  lines.push('');

  const out = path.join(srcDir, 'ADR-INDEX.md');
  fs.writeFileSync(out, lines.join('\n'));
  console.log(`✓ ADR index written → ${out}  (${adrs.length} ADRs)`);
  return true;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

if (!fs.existsSync(outerRepo)) {
  console.error(`Error: outer repo not found at ${outerRepo}`);
  console.error('Pass --outer-repo <path> to specify a different location.');
  process.exit(1);
}

if (!adrOnly)  generateBookIndex();
if (!bookOnly) generateAdrIndex();
