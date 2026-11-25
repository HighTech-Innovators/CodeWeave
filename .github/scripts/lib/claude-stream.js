#!/usr/bin/env node
/**
 * claude-stream.js SESSION_MD
 *
 * Renders `claude -p … --output-format stream-json --verbose` (stderr merged in)
 * for the pipeline:
 *   stdout      readable progress: the agent's messages and one line per tool
 *               call. The phase script tees this into the pass's proof log.
 *   SESSION_MD  the session transcript (the Claude counterpart of Copilot's
 *               --share file): every message and tool call, tool results
 *               truncated to MAX_RESULT characters.
 *
 * Exits 1 when the session ended in an error or produced no result.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const readline = require('readline');

const MAX_RESULT = 4000;
const sessionPath = process.argv[2];
const sessionFd = sessionPath ? fs.openSync(sessionPath, 'w') : null;
const md = text => { if (sessionFd !== null) fs.writeSync(sessionFd, text + '\n'); };
const cwd = process.cwd();
const rel = p => (typeof p === 'string' && p.startsWith(cwd + path.sep) ? p.slice(cwd.length + 1) : p);
const fence = text => '~~~~\n' + text + '\n~~~~';

function describeTool(name, input = {}) {
  switch (name) {
    case 'Read':  return rel(input.file_path) + (input.offset ? ` (from line ${input.offset})` : '');
    case 'Write': return `${rel(input.file_path)} (${(input.content || '').length} chars)`;
    case 'Edit':  return rel(input.file_path);
    case 'Glob':  return input.pattern + (input.path ? ` in ${rel(input.path)}` : '');
    case 'Grep':  return `/${input.pattern}/` + (input.path ? ` in ${rel(input.path)}` : '') + (input.glob ? ` [${input.glob}]` : '');
    default:      return JSON.stringify(input).slice(0, 200);
  }
}

function toolResultText(content) {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) return content.map(c => (c.type === 'text' ? c.text : `[${c.type}]`)).join('\n');
  return JSON.stringify(content);
}

const toolNames = new Map();   // tool_use_id → tool name
let result = null;

const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });

rl.on('line', line => {
  if (!line.trim()) return;
  let ev;
  try {
    ev = JSON.parse(line);
  } catch {
    console.log(line);            // stderr text or anything that is not an event
    md(fence(line));
    return;
  }

  if (ev.type === 'system' && ev.subtype === 'init') {
    const tools = (ev.tools || []).join(', ');
    console.log(`Claude Code ${ev.claude_code_version || ''} · model ${ev.model} · tools: ${tools} · session ${ev.session_id}`);
    md(`# Claude Code session \`${ev.session_id}\`\n`);
    md(`- Model: ${ev.model}\n- Tools: ${tools}\n- Permission mode: ${ev.permissionMode}\n- Working directory: ${ev.cwd}\n`);
    return;
  }

  if (ev.type === 'assistant') {
    for (const c of (ev.message && ev.message.content) || []) {
      if (c.type === 'text' && c.text.trim()) {
        console.log(c.text);
        md(`\n## Assistant\n\n${c.text}\n`);
      } else if (c.type === 'tool_use') {
        toolNames.set(c.id, c.name);
        const what = describeTool(c.name, c.input);
        console.log(`→ ${c.name} ${what}`);
        md(`\n**${c.name}** \`${what}\``);
      }
    }
    return;
  }

  if (ev.type === 'user') {
    for (const c of (ev.message && ev.message.content) || []) {
      if (c.type !== 'tool_result') continue;
      const text = toolResultText(c.content);
      if (c.is_error) {
        console.log(`  ✗ ${toolNames.get(c.tool_use_id) || 'tool'} failed: ${text.split('\n')[0].slice(0, 200)}`);
      }
      const shown = text.length > MAX_RESULT
        ? `${text.slice(0, MAX_RESULT)}\n… (${text.length - MAX_RESULT} more characters)`
        : text;
      md(`\n${c.is_error ? 'Error' : 'Result'}:\n\n${fence(shown)}`);
    }
    return;
  }

  if (ev.type === 'result') {
    result = ev;
    const seconds = Math.round((ev.duration_ms || 0) / 1000);
    const cost = typeof ev.total_cost_usd === 'number' ? ` · $${ev.total_cost_usd.toFixed(2)} API-equivalent` : '';
    const denied = (ev.permission_denials || []).length;
    const outcome = ev.is_error ? `failed (${ev.subtype})` : 'finished';
    const summary = `Session ${outcome} · ${ev.num_turns} turns · ${seconds}s${cost}` +
      (denied ? ` · ${denied} tool call(s) refused` : '');
    console.log(`\n${summary}`);
    md(`\n---\n\n${summary}`);
    if (ev.is_error && ev.result) console.log(ev.result);
  }
  // Other event types (rate_limit_event, stream partials, …) are not rendered.
});

rl.on('close', () => {
  if (!result) console.log('\nClaude Code ended without a result event.');
  if (sessionFd !== null) fs.closeSync(sessionFd);
  process.exit(result && !result.is_error ? 0 : 1);
});
