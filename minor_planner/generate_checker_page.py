"""
Generate checker.html — interactive minor progress checker page.
Reads checker_data.json and produces a self-contained static HTML page.

Usage:  python generate_checker_page.py
"""

import json
from pathlib import Path

BASE = Path(__file__).parent.parent
DATA_FILE = BASE / "site" / "data" / "checker_data.json"
OUTPUT_FILE = BASE / "site" / "checker.html"

CHECKER_CSS = """\
:root { --bg: #f8f9fa; --card: #fff; --border: #dee2e6; --accent: #2563eb;
        --text: #212529; --muted: #6c757d; --green: #16a34a; --green-bg: #f0fdf4;
        --red: #dc2626; --warn: #b45309; --warn-bg: #fff8f0;
        --tbl-border: #868a90; --tbl-border-light: #d5d8dc; }
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
       background:var(--bg); color:var(--text); line-height:1.6; }
.container { max-width:960px; margin:0 auto; padding:20px; }
h1 { font-size:1.7em; margin-bottom:.3em; }
h2 { font-size:1.2em; margin:1.2em 0 .5em; padding-bottom:4px;
     border-bottom:1px solid var(--border); color:#333; }
a { color:var(--accent); text-decoration:none; }
a:hover { text-decoration:underline; }
.back-link { font-size:.9em; margin-bottom:1em; display:inline-block; }
.section { background:var(--card); padding:14px 18px; border-radius:8px;
           border:1px solid var(--border); margin-bottom:12px; }
.section textarea { width:100%; min-height:200px; font-family:'Courier New',monospace;
    font-size:.85em; padding:10px; border:1px solid var(--border); border-radius:6px;
    resize:vertical; }
.btn { display:inline-block; padding:10px 24px; background:var(--accent);
       color:#fff; border:none; border-radius:6px; font-size:1em; cursor:pointer;
       font-weight:500; }
.btn:hover { opacity:.9; }
.btn:disabled { opacity:.5; cursor:default; }
.summary { font-size:.9em; color:var(--muted); margin:.5em 0 1em; }
.summary strong { color:var(--text); }

/* Results */
.result-card { background:var(--card); border-radius:8px; border:1px solid var(--border);
    margin-bottom:10px; overflow:hidden; transition:border-color .15s; }
.result-card:hover { border-color:var(--accent); }
.result-header { display:flex; align-items:center; padding:12px 16px; cursor:pointer;
    gap:12px; }
.result-header:hover { background:#fafafa; }
.result-rank { font-size:1.1em; font-weight:700; color:var(--muted); min-width:2em;
    text-align:center; }
.result-info { flex:1; min-width:0; }
.result-title { font-weight:600; }
.result-meta { font-size:.82em; color:var(--muted); }
.result-bar-wrap { width:180px; flex-shrink:0; }
.result-bar-bg { height:8px; background:#e5e7eb; border-radius:4px; overflow:hidden; }
.result-bar-fill { height:100%; border-radius:4px; transition:width .3s; }
.result-pct { font-size:.85em; font-weight:600; min-width:3.5em; text-align:right; }
.result-arrow { font-size:.8em; color:var(--muted); }

/* Detail expansion */
.result-detail { display:none; padding:0 16px 14px; border-top:1px solid var(--border); }
.result-detail.open { display:block; }
.detail-section { margin-top:10px; }
.detail-section h4 { font-size:.95em; margin-bottom:6px; color:#555; }
.detail-row { padding:6px 0; font-size:.88em; }
.detail-row-text { color:var(--muted); margin-bottom:4px; }
.detail-course-list { display:flex; flex-wrap:wrap; gap:4px; }
.detail-course { display:inline-block; padding:2px 8px; border-radius:4px;
    font-size:.82em; font-family:'Courier New',monospace; border:1px solid var(--border); }
.detail-course.matched { background:var(--green-bg); border-color:var(--green);
    color:var(--green); }
.detail-course.equiv { background:#fef2f2; border-color:#dc2626;
    color:#dc2626; }
.detail-row-stat { font-size:.82em; color:var(--muted); margin-top:2px; }

/* Colors for progress */
.bar-high { background:var(--green); }
.bar-mid { background:#eab308; }
.bar-low { background:var(--red); }
.pct-high { color:var(--green); }
.pct-mid { color:#b45309; }
.pct-low { color:var(--red); }

table { width:100%; border-collapse:collapse; background:var(--card);
    border-radius:8px; overflow:hidden; border:1px solid var(--border); margin-bottom:12px; }
th,td { padding:7px 10px; text-align:left; border-bottom:1px solid var(--tbl-border);
    font-size:.85em; }
th:first-child, td:first-child { white-space:nowrap; }
th:nth-child(3), td:nth-child(3) { white-space:nowrap; text-align:center; }
th { background:#fafafa; font-weight:600; color:#555; }
tr:hover { background:#f9f9f9; }
tr.matched { background:var(--green-bg); }
tr.matched:hover { background:#e6f7ea; }

.disclaimer { margin-top:24px; padding:12px 16px; border-left:3px solid var(--warn);
    font-size:.82em; color:var(--muted); background:var(--warn-bg); border-radius:4px; }

.site-footer { margin-top:20px; padding-top:12px; border-top:1px solid var(--border);
    font-size:.82em; color:var(--muted); text-align:center; }
.site-footer a { color:var(--muted); }
.site-footer a:hover { color:var(--accent); }

@media (max-width:768px) {
    .container { padding:12px; }
    h1 { font-size:1.3em; }
    .result-header { flex-wrap:wrap; }
    .result-bar-wrap { width:100%; order:3; margin-top:4px; }
    .result-pct { order:2; }
}
"""

CHECKER_JS = r"""
// ── Parser ───────────────────────────────────────────────────────────────
function parseCourses(text) {
  // Normalize input: add space after 4-letter subject codes when missing
  // e.g. "AIST3020" -> "AIST 3020", "aist1110" -> "AIST 1110"
  var normalized = text.replace(/([A-Za-z]{4})(\d{4})/g, function(m, dept, num) {
    return dept.toUpperCase() + ' ' + num;
  });
  // Extract all DEPT XXXX patterns
  var seen = {};
  var courses = [];
  var codes = normalized.match(/[A-Z]{4}\s\d{4}/g);
  if (codes) {
    for (var i = 0; i < codes.length; i++) {
      var c = codes[i];
      if (!seen[c]) {
        seen[c] = true;
        var info = (typeof CHECKER_DATA !== 'undefined' && CHECKER_DATA.courses && CHECKER_DATA.courses[c]) || {};
        courses.push({
          code: c,
          title: info.title || '',
          unit: info.unit || 0
        });
      }
    }
  }
  return courses;
}

// ── Canonicalizer ───────────────────────────────────────────────────────
function makeCanonicalizer(eqNorm) {
  return function(code) {
    var root = eqNorm[code];
    if (root) {
      // Follow chain to root (Python UF already resolves, but be safe)
      while (eqNorm[root]) root = eqNorm[root];
      return root;
    }
    return code;
  };
}

// ── Matching Engine ─────────────────────────────────────────────────────
function courseLevel(code) {
  var parts = code.split(' ');
  if (parts.length < 2) return 0;
  return parseInt(parts[1]) || 0;
}

function countLevelMatches(matchedCodes, levelConstraint, studentUnits) {
  var minLevel = levelConstraint.min_level || 0;
  var maxLevel = levelConstraint.max_level; // null means no upper bound
  var total = 0;
  var count = 0;
  for (var i = 0; i < matchedCodes.length; i++) {
    var c = matchedCodes[i];
    var lvl = courseLevel(c);
    var within = lvl >= minLevel;
    if (maxLevel !== null && maxLevel !== undefined) within = within && lvl <= maxLevel;
    if (within) {
      total += (studentUnits[c] || 0);
      count += 1;
    }
  }
  return {units: total, count: count};
}

function matchRow(row, studentCanonSet, studentUnits, canonFn) {
  // Canonicalize and deduplicate requirement codes
  var seen = {};
  var reqCanon = [];
  for (var i = 0; i < row.codes.length; i++) {
    var c = row.codes[i];
    var canon = canonFn(c.code);
    if (!seen[canon]) {
      seen[canon] = true;
      reqCanon.push({canon: canon, unit: c.unit, orig: c.code});
    }
  }

  // Match canonical codes
  var matchedCanon = [];
  var matchedUnits = 0;
  for (var i = 0; i < reqCanon.length; i++) {
    var rc = reqCanon[i];
    if (studentCanonSet[rc.canon]) {
      matchedCanon.push(rc.canon);
      matchedUnits += (studentUnits[rc.canon] || rc.unit || 3);
    }
  }

  // Track which row codes are student's exact course vs equivalent
  var matchedExact = {};  // green
  var matchedEquiv = {};  // red (equivalent but not exact)
  for (var i = 0; i < row.codes.length; i++) {
    var oc = row.codes[i];
    var ocanon = canonFn(oc.code);
    if (!studentCanonSet[ocanon]) continue;
    // Check if student has this exact code (not just an equivalent)
    if (studentCanonSet._exact && studentCanonSet._exact[oc.code]) {
      matchedExact[oc.code] = true;
    } else {
      matchedEquiv[oc.code] = true;
    }
  }

  var strategy = row.strategy;
  var satisfied = false;
  var progress = 0;
  var rowTarget = 0;
  var rowEarned = 0;

  if (strategy === 'all') {
    satisfied = matchedCanon.length === reqCanon.length && reqCanon.length > 0;
    rowTarget = reqCanon.reduce(function(s, c) { return s + (c.unit || 3); }, 0);
    rowEarned = matchedUnits;
    progress = reqCanon.length > 0 ? matchedCanon.length / reqCanon.length : 0;
  } else if (strategy === 'pick_n') {
    var n = row.n || 1;
    satisfied = matchedCanon.length >= n;
    progress = Math.min(matchedCanon.length, n) / n;
    var avgUnit = reqCanon.length > 0
      ? reqCanon.reduce(function(s, c) { return s + (c.unit || 3); }, 0) / reqCanon.length : 3;
    rowTarget = n * avgUnit;
    rowEarned = Math.min(matchedCanon.length, n) * avgUnit;
  } else if (strategy === 'units') {
    var needed = row.units_needed || 0;
    var lcOk = true;
    if (row.level_constraint) {
      var lc = row.level_constraint;
      var lv = countLevelMatches(matchedCanon, lc, studentUnits);
      if (lc.min_units_needed) lcOk = lcOk && lv.units >= lc.min_units_needed;
      if (lc.min_courses_needed) lcOk = lcOk && lv.count >= lc.min_courses_needed;
    }
    satisfied = matchedUnits >= needed && lcOk;
    progress = needed > 0 ? Math.min(matchedUnits, needed) / needed : 0;
    rowTarget = needed;
    rowEarned = Math.min(matchedUnits, needed);
  } else if (strategy === 'or_group') {
    // Find best group
    var bestProgress = 0, bestSatisfied = false, bestTarget = 0;
    var bestMatchedCanon = [], bestMatchedUnits = 0;

    for (var gi = 0; gi < (row.or_groups || []).length; gi++) {
      var g = row.or_groups[gi];
      var gSeen = {}, gCanon = [];
      for (var ci = 0; ci < g.codes.length; ci++) {
        var gcanon = canonFn(g.codes[ci]);
        if (!gSeen[gcanon]) { gSeen[gcanon] = true; gCanon.push(gcanon); }
      }
      var gMatched = [];
      var gUnits = 0;
      for (var ci = 0; ci < gCanon.length; ci++) {
        if (studentCanonSet[gCanon[ci]]) {
          gMatched.push(gCanon[ci]);
          gUnits += (studentUnits[gCanon[ci]] || 3);
        }
      }
      var gProgress = gCanon.length > 0 ? gMatched.length / gCanon.length : 0;
      var gSatisfied = gMatched.length === gCanon.length && gCanon.length > 0;

      if (gProgress > bestProgress) {
        bestProgress = gProgress; bestSatisfied = gSatisfied;
        bestTarget = gCanon.reduce(function(s, c) { return s + 3; }, 0);
        bestMatchedCanon = gMatched; bestMatchedUnits = gUnits;
      }
    }
    satisfied = bestSatisfied;
    progress = bestProgress;
    matchedCanon = bestMatchedCanon;
    matchedUnits = bestMatchedUnits;
    rowTarget = bestTarget;
    rowEarned = bestSatisfied ? bestTarget : 0;
    rowTarget = row.units_needed || bestTarget; // use precomputed min target
  } else if (strategy === 'any') {
    satisfied = false;
    progress = 0;
    rowTarget = 0;
    rowEarned = 0;
  }

  return {
    text: row.text,
    strategy: strategy,
    codes: row.codes,
    dedup_count: row.dedup_count || row.codes.length,
    or_groups: row.or_groups,
    matched: matchedCanon,
    matchedUnits: matchedUnits,
    matchedExact: matchedExact,
    matchedEquiv: matchedEquiv,
    satisfied: satisfied,
    progress: progress,
    rowTarget: rowTarget,
    rowEarned: rowEarned,
    n: row.n,
    units_needed: row.units_needed,
    level_constraint: row.level_constraint
  };
}

function scoreMinor(minorData, studentCourses, courseIndex) {
  var canonFn = makeCanonicalizer(minorData.eq_norm);

  // Build student canonical set and unit map
  var studentCanonSet = {_exact: {}};
  var studentUnits = {};
  for (var i = 0; i < studentCourses.length; i++) {
    var c = studentCourses[i];
    var canon = canonFn(c.code);
    studentCanonSet[canon] = true;
    studentCanonSet._exact[c.code] = true;
    // Use course_info unit or default to 3
    var infoUnit = (courseIndex[c.code] && courseIndex[c.code].unit) || 0;
    studentUnits[canon] = Math.max(c.unit, infoUnit, 0) || 3;
  }

  var sections = [];
  var totalTarget = 0;
  var totalEarned = 0;

  for (var si = 0; si < minorData.sections.length; si++) {
    var sec = minorData.sections[si];
    var secTarget = sec.target_units || 0;
    var secEarned = 0;
    var rows = [];

    for (var ri = 0; ri < sec.rows.length; ri++) {
      var mr = matchRow(sec.rows[ri], studentCanonSet, studentUnits, canonFn);
      secEarned += mr.rowEarned;
      rows.push(mr);
    }

    secEarned = Math.min(secEarned, secTarget || secEarned + 1); // cap at target
    totalTarget += secTarget;
    totalEarned += secEarned;

    sections.push({
      label: sec.label,
      target_units: secTarget,
      earned_units: secEarned,
      progress: secTarget > 0 ? secEarned / secTarget : 0,
      rows: rows
    });
  }

  var overall = totalTarget > 0 ? totalEarned / totalTarget : 0;

  return {
    title: minorData.title,
    faculty: minorData.faculty,
    description: minorData.description || '',
    sections: sections,
    overall_progress: overall,
    total_target: totalTarget,
    total_earned: totalEarned
  };
}

// ── UI Rendering ────────────────────────────────────────────────────────

function getProgressColorClass(pct) {
  if (pct >= 0.8) return 'high';
  if (pct >= 0.4) return 'mid';
  return 'low';
}

function buildResultCard(result, index) {
  var pct = result.overall_progress;
  var pctDisplay = Math.round(pct * 100);
  var cls = getProgressColorClass(pct);

  var html = '<div class="result-card" id="card-' + index + '">';
  html += '<div class="result-header" onclick="toggleDetail(' + index + ')">';
  html += '<span class="result-rank">' + (index + 1) + '</span>';
  html += '<div class="result-info">';
  html += '<div class="result-title">' + result.title + '</div>';
  html += '<div class="result-meta">' + result.faculty + '</div>';
  html += '</div>';
  html += '<div class="result-bar-wrap"><div class="result-bar-bg"><div class="result-bar-fill bar-' + cls + '" style="width:' + pctDisplay + '%"></div></div></div>';
  html += '<span class="result-pct pct-' + cls + '">' + pctDisplay + '%</span>';
  html += '<span class="result-arrow" id="arrow-' + index + '">&#9660;</span>';
  html += '</div>';

  // Detail section
  html += '<div class="result-detail" id="detail-' + index + '">';
  if (result.description) {
    html += '<div class="detail-row" style="margin-bottom:10px;color:var(--muted);font-size:.88em;">' + result.description + '</div>';
  }
  for (var si = 0; si < result.sections.length; si++) {
    var sec = result.sections[si];
    var secPct = Math.round(sec.progress * 100);
    html += '<div class="detail-section">';
    html += '<h4>' + sec.label + ' (' + secPct + '%)</h4>';

    for (var ri = 0; ri < sec.rows.length; ri++) {
      var row = sec.rows[ri];
      var rPct = Math.round(row.progress * 100);
      html += '<div class="detail-row">';
      html += '<div class="detail-row-text">' + row.text + ' <strong>(';
      if (row.strategy === 'pick_n') {
        html += row.matched.length + '/' + row.n + ' courses';
      } else if (row.strategy === 'units') {
        html += row.matchedUnits.toFixed(1) + '/' + (row.units_needed || 0) + ' units';
      } else if (row.strategy === 'all') {
        var dcount = row.dedup_count || row.codes.length;
        html += row.matched.length + '/' + dcount + ' courses';
      } else if (row.strategy === 'or_group') {
        var bestGroup = 0;
        var bestProg = 0;
        if (row.or_groups) {
          for (var gi = 0; gi < row.or_groups.length; gi++) {
            var gd = row.or_groups[gi].dedup_count || row.or_groups[gi].codes.length;
            var gm = 0;
            for (var ci = 0; ci < row.or_groups[gi].codes.length; ci++) {
              if ((row.matchedExact && row.matchedExact[row.or_groups[gi].codes[ci]]) ||
                  (row.matchedEquiv && row.matchedEquiv[row.or_groups[gi].codes[ci]])) gm++;
            }
            if (gd > 0 && gm/gd > bestProg) { bestProg = gm/gd; bestGroup = gi; }
          }
        }
        html += 'Best group: ' + Math.round(bestProg * 100) + '%';
      } else if (row.strategy === 'any') {
        var secTarget = sec.target_units || 0;
        if (secTarget > 0) {
          html += row.matched.length + ' courses overlap (section: ' + secTarget.toFixed(1) + ' units)';
        } else {
          html += row.matched.length + ' courses overlap';
        }
      }
      html += ')</strong></div>';

      // Course chips — always show all
      if (row.codes.length > 0) {
        html += '<div class="detail-course-list">';
        for (var ci = 0; ci < row.codes.length; ci++) {
          var codeObj = row.codes[ci];
          var cls2 = 'detail-course';
          if (row.matchedExact && row.matchedExact[codeObj.code]) {
            cls2 += ' matched';
          } else if (row.matchedEquiv && row.matchedEquiv[codeObj.code]) {
            cls2 += ' equiv';
          }
          html += '<span class="' + cls2 + '">' + codeObj.code + '</span>';
        }
        html += '</div>';
      }

      if (row.level_constraint) {
        var lc = row.level_constraint;
        var lv = 'Level ' + lc.min_level;
        if (lc.max_level) lv += '-' + lc.max_level;
        if (lc.min_units_needed) lv += ': need ' + lc.min_units_needed + ' units';
        if (lc.min_courses_needed) lv += ': need ' + lc.min_courses_needed + ' courses';
        html += '<div class="detail-row-stat">&#9888; Level constraint: ' + lv + '</div>';
      }

      html += '</div>';
    }
    html += '</div>';
  }
  html += '</div>';
  html += '</div>';
  return html;
}

function toggleDetail(index) {
  var detail = document.getElementById('detail-' + index);
  var arrow = document.getElementById('arrow-' + index);
  if (!detail) return;
  var isOpen = detail.classList.contains('open');
  // Close all others
  var allDetails = document.querySelectorAll('.result-detail');
  for (var i = 0; i < allDetails.length; i++) allDetails[i].classList.remove('open');
  var allArrows = document.querySelectorAll('.result-arrow');
  for (var i = 0; i < allArrows.length; i++) allArrows[i].innerHTML = '&#9660;';
  if (!isOpen) {
    detail.classList.add('open');
    arrow.innerHTML = '&#9650;';
    detail.scrollIntoView({behavior:'smooth',block:'nearest'});
  }
}

function renderResults(results) {
  var container = document.getElementById('results');
  if (!container) return;

  // Sort by progress descending
  results.sort(function(a, b) { return b.overall_progress - a.overall_progress; });

  var html = '<h2>Results</h2>';
  html += '<p class="summary">' + results.length + ' minors evaluated &middot; sorted by completion</p>';

  for (var i = 0; i < results.length; i++) {
    html += buildResultCard(results[i], i);
  }

  // Disclaimer
  html += '<div class="disclaimer">' +
    '<strong>Accuracy note:</strong> This tool checks your courses against published minor programme ' +
    'requirements. Some requirements involving exemptions, cross-references, or programme-specific ' +
    'rules (e.g., double-counting caps with your major) cannot be fully evaluated. ' +
    'Always verify with your academic advisor.' +
    '</div>';

  container.innerHTML = html;
}

// ── Main Controller ────────────────────────────────────────────────────

var PARSED_COURSES = [];
var ALL_RESULTS = [];

function doParse() {
  var textarea = document.getElementById('input-text');
  var text = textarea.value;
  if (!text.trim()) return;

  // Save to localStorage
  try { localStorage.setItem('checkerCUSIS', text); } catch(e) {}

  PARSED_COURSES = parseCourses(text);

  var summary = document.getElementById('parse-summary');
  var tableContainer = document.getElementById('course-table');

  if (PARSED_COURSES.length === 0) {
    summary.innerHTML = 'No valid CUHK course codes found. Paste the full CUSIS academic records page text.';
    tableContainer.innerHTML = '';
    document.getElementById('parse-section').style.display = 'none';
    document.getElementById('results').innerHTML = '';
    return;
  }

  document.getElementById('parse-section').style.display = 'block';

  var totalUnits = PARSED_COURSES.reduce(function(s, c) { return s + c.unit; }, 0);

  // Auto-open the parsed details and update summary
  var parsedDetail = document.getElementById('parsed-detail');
  if (parsedDetail) parsedDetail.open = true;
  var summaryEl = document.getElementById('parse-summary');
  if (summaryEl) summaryEl.innerHTML = PARSED_COURSES.length + ' courses, ' + totalUnits.toFixed(1) + ' units';
  var icon = document.querySelector('#parse-section .toggle-icon');
  if (icon) icon.innerHTML = '&#9660;';

  // Build course table
  var tbl = '<table><thead><tr><th>Code</th><th>Title</th><th>Units</th></tr></thead><tbody>';
  for (var i = 0; i < PARSED_COURSES.length; i++) {
    var c = PARSED_COURSES[i];
    tbl += '<tr><td>' + c.code + '</td><td>' + (c.title || '(not in catalog)') + '</td><td>' + c.unit.toFixed(1) + '</td></tr>';
  }
  tbl += '</tbody></table>';
  tableContainer.innerHTML = tbl;

  // Process all minors
  if (typeof CHECKER_DATA === 'undefined') {
    document.getElementById('results').innerHTML = '<p class="summary">Error: minor data not loaded.</p>';
    return;
  }

  var courseIndex = CHECKER_DATA.courses || {};
  var minors = CHECKER_DATA.minors || {};

  ALL_RESULTS = [];
  for (var key in minors) {
    var result = scoreMinor(minors[key], PARSED_COURSES, courseIndex);
    ALL_RESULTS.push(result);
  }

  renderResults(ALL_RESULTS);
}

// ── Init ────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function() {
  // Restore saved text
  try {
    var saved = localStorage.getItem('checkerCUSIS');
    if (saved) {
      document.getElementById('input-text').value = saved;
    }
  } catch(e) {}

  document.getElementById('btn-parse').addEventListener('click', doParse);

  // Auto-parse if there's saved text
  var textarea = document.getElementById('input-text');
  if (textarea.value.trim()) {
    // Don't auto-parse — let user click the button
  }
});
"""

CHECKER_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Minor Progress Checker - CUHK</title>
<style>{css}</style>
</head>
<body>
<div class="container">
  <a href="index.html" class="back-link">&larr; Back to Minor Programmes</a>
  <h1>Minor Progress Checker</h1>
  <p class="summary">Paste your CUSIS academic records to find which CUHK minor programmes you are closest to completing.</p>

  <div class="section">
    <h2>1. Paste CUSIS Academic Records</h2>
    <p class="summary">Go to CUSIS &rarr; Academic Records &rarr; View All, then copy all text (Ctrl+A, Ctrl+C) and paste below.</p>
    <textarea id="input-text" placeholder="AIST 3020&#10;Intro to Computer Systems&#10;2025-26 Term 2&#10;A&#10;3.00&#10;TakenTaken&#10;..."></textarea>
    <button class="btn" id="btn-parse" style="margin-top:8px;">Analyze Progress</button>
  </div>

  <div class="section" id="parse-section" style="display:none;">
    <h2 style="margin:0;cursor:pointer;" onclick="var d=document.getElementById('parsed-detail');d.open=!d.open;var i=this.querySelector('.toggle-icon');i.innerHTML=d.open?'&#9660;':'&#9654;';">
      <span class="toggle-icon">&#9654;</span> 2. Parsed Courses &mdash; <span id="parse-summary"></span>
    </h2>
    <details id="parsed-detail">
      <summary style="display:none;"></summary>
      <div id="course-table"></div>
    </details>
  </div>

  <div id="results"></div>

  <div class="site-footer">
    <a href="index.html">CUHK Minor Programmes</a>
    <span> &middot; </span>
    <a href="https://rgsntl.rgs.cuhk.edu.hk/aqs_prd_applx/Public/tt_dsp_acad_prog.aspx" target="_blank" rel="noopener">CUHK program info</a>
  </div>
</div>
<script>
var CHECKER_DATA = {checker_data_json};
</script>
<script>
{js}
</script>
</body>
</html>"""


def generate():
    if not DATA_FILE.exists():
        print(f"Error: {DATA_FILE} not found. Run generate_checker_data.py first.")
        return

    checker_data = DATA_FILE.read_text(encoding="utf-8")

    html = CHECKER_HTML_TEMPLATE.format(
        css=CHECKER_CSS,
        checker_data_json=checker_data,
        js=CHECKER_JS,
    )

    OUTPUT_FILE.write_text(html, encoding="utf-8")
    print(f"Generated: {OUTPUT_FILE}")
    print(f"  Size: {len(html) / 1024:.0f} KB")


if __name__ == "__main__":
    generate()
