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
.detail-course.elsewhere { background:#fefce8; border-color:#eab308;
    color:#b45309; }
.detail-course.waived { background:#f0f4f8; border-color:#94a3b8;
    color:#64748b; }
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

/* Explanatory notes — matches info-page styling */
.detail-notes { margin:14px 0 0; }
.detail-notes h4 { font-size:.95em; margin-bottom:6px; color:#555; }
.detail-notes .section { background:var(--card); padding:14px 18px; border-radius:8px;
    border:1px solid var(--border); margin-bottom:12px; }
.detail-notes .notes-point { display:flex; align-items:flex-start; gap:10px;
    padding:10px 14px; cursor:default; transition:background .15s; }
.detail-notes .notes-point:hover { background:#f0f4ff; }
.detail-notes .point-idx { font-weight:600; color:var(--accent); min-width:22px;
    flex-shrink:0; font-size:.82em; }
.detail-notes .point-text { flex:1; font-size:.82em; line-height:1.55; color:var(--text); }
.detail-notes .point-text p { margin:0; }
.detail-notes .notes-table-section { overflow-x:auto; border-radius:8px; }
.detail-notes .notes-table-section table { background:var(--card);
    border-collapse:collapse; border-radius:8px; overflow:hidden; width:100%; }
.detail-notes .notes-table-section td { padding:9px 13px;
    border-bottom:1px solid var(--tbl-border); font-size:.82em; color:var(--text); }
.detail-notes .notes-table-section tr:hover { background:#f9f9f9; }

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
          unit: info.unit || 3
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

// ── Level constraint helpers ──────────────────────────────────────────────
function checkAllLevelConstraints(matchedCanon, constraints, studentUnits) {
  if (!constraints || !constraints.length) return {allOk: true, results: [], strictest: null};
  var allOk = true, results = [], strictest = null, minProgress = 1;
  for (var i = 0; i < constraints.length; i++) {
    var lc = constraints[i];
    var lv = countLevelMatches(matchedCanon, lc, studentUnits);
    var ok = true;
    if (lc.min_units_needed) ok = ok && lv.units >= lc.min_units_needed;
    if (lc.min_courses_needed) ok = ok && lv.count >= lc.min_courses_needed;
    allOk = allOk && ok;
    // Track progress per constraint
    var cp = 1;
    if (lc.min_units_needed && lc.min_units_needed > 0) cp = Math.min(lv.units, lc.min_units_needed) / lc.min_units_needed;
    if (lc.min_courses_needed && lc.min_courses_needed > 0) cp = Math.min(cp, lv.count / lc.min_courses_needed);
    minProgress = Math.min(minProgress, cp);
    results.push({lc: lc, lv: lv, ok: ok, progress: cp});
    var hasCount = !!(lc.min_units_needed || lc.min_courses_needed);
    var prevHasCount = strictest && !!(strictest.lc.min_units_needed || strictest.lc.min_courses_needed);
    if (!strictest || (hasCount && !prevHasCount) ||
        (hasCount === prevHasCount && (lc.min_level || 0) > (strictest.lc.min_level || 0)))
      strictest = {lc: lc, lv: lv, ok: ok};
  }
  return {allOk: allOk, results: results, strictest: strictest, minProgress: minProgress};
}

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

function matchRow(row, studentCanonSet, studentUnits, studentRawUnits, canonFn, excludeCanon, studentUnitList, globalMinLevel) {
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

  // Match canonical codes (skip excluded, but allow spillover when units remain)
  var matchedCanon = [];
  var matchedUnits = 0;
  for (var i = 0; i < reqCanon.length; i++) {
    var rc = reqCanon[i];
    var consumedAlready = excludeCanon ? (excludeCanon[rc.canon] || 0) : 0;
    var totalAvail = (studentRawUnits[rc.canon] || studentUnits[rc.canon] || rc.unit || 3);
    if (studentCanonSet[rc.canon] && consumedAlready < totalAvail) {
      matchedCanon.push(rc.canon);
      matchedUnits += Math.min(totalAvail - consumedAlready, (studentUnits[rc.canon] || rc.unit || 3));
    }
  }

  // Track raw student units (per canonical, accounting for multiple equivalent courses entered)
  var rawStudentUnitsTotal = 0;
  var rawSeen = {};
  for (var i = 0; i < reqCanon.length; i++) {
    var rc = reqCanon[i];
    if (studentCanonSet[rc.canon] && !rawSeen[rc.canon]) {
      rawSeen[rc.canon] = true;
      rawStudentUnitsTotal += (studentRawUnits[rc.canon] || studentUnits[rc.canon] || rc.unit || 3);
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
      // Only mark as equiv if the canonical still has remaining units
      var consumeME = excludeCanon ? (excludeCanon[ocanon] || 0) : 0;
      var totalME = studentRawUnits[ocanon] || studentUnits[ocanon] || 3;
      if (consumeME < totalME) {
        matchedEquiv[oc.code] = true;
      }
    }
  }

  // Determine if there are true equivalent matches not already covered
  // by an exact match in the same equivalence class
  var exactCanon = {};
  for (var i = 0; i < row.codes.length; i++) {
    if (matchedExact[row.codes[i].code]) {
      exactCanon[canonFn(row.codes[i].code)] = true;
    }
  }
  var hasTrueEquivMatch = false;
  for (var i = 0; i < row.codes.length; i++) {
    if (matchedEquiv[row.codes[i].code] && !exactCanon[canonFn(row.codes[i].code)]) {
      hasTrueEquivMatch = true;
      break;
    }
  }

  var strategy = row.strategy;
  var satisfied = false;
  var progress = 0;

  // Sort matched courses: level-constraint-meeting first, then higher unit
  if (strategy === 'units' || strategy === 'pick_n') {
    // Use smallest min_level from row LC or global LC as threshold
    // and only prioritize as many courses as the constraints actually need.
    var sortMinLevel = 0;
    var sortMaxPriority = Infinity; // max courses to prioritize by level
    if (row.level_constraint) {
      var slcList = Array.isArray(row.level_constraint) ? row.level_constraint : [row.level_constraint];
      sortMinLevel = slcList[0].min_level || 0;
      for (var sli = 1; sli < slcList.length; sli++) {
        if (slcList[sli].min_level && slcList[sli].min_level < sortMinLevel) sortMinLevel = slcList[sli].min_level;
      }
      // Find the max needed courses across all constraints (only prioritize that many)
      for (var sli = 0; sli < slcList.length; sli++) {
        if (slcList[sli].min_level >= sortMinLevel && slcList[sli].min_courses_needed) {
          sortMaxPriority = Math.min(sortMaxPriority, slcList[sli].min_courses_needed);
        }
      }
      if (sortMaxPriority === Infinity) sortMaxPriority = 0;
    }
    if (globalMinLevel && (!sortMinLevel || globalMinLevel < sortMinLevel)) {
      sortMinLevel = globalMinLevel;
      sortMaxPriority = Infinity; // global constraint may need all matching courses
    }
    // Separate into two groups: high-priority (first sortMaxPriority level-matching
    // courses by unit desc), then everything else by unit desc.
    var hiPriority = [], loPriority = [];
    if (sortMinLevel > 0 && sortMaxPriority > 0) {
      for (var si = 0; si < matchedCanon.length; si++) {
        var canon = matchedCanon[si];
        if (courseLevel(canon) >= sortMinLevel) hiPriority.push(canon);
        else loPriority.push(canon);
      }
      hiPriority.sort(function(a, b) { return (studentUnits[b] || 3) - (studentUnits[a] || 3); });
      loPriority.sort(function(a, b) { return (studentUnits[b] || 3) - (studentUnits[a] || 3); });
      matchedCanon = hiPriority.slice(0, sortMaxPriority).concat(loPriority).concat(hiPriority.slice(sortMaxPriority));
    } else {
      matchedCanon.sort(function(a, b) {
        if (sortMinLevel > 0) {
          var aMeets = courseLevel(a) >= sortMinLevel;
          var bMeets = courseLevel(b) >= sortMinLevel;
          if (aMeets !== bMeets) return bMeets - aMeets;
        }
        return (studentUnits[b] || 3) - (studentUnits[a] || 3);
      });
    }
  }
  var rowTarget = 0;
  var rowEarned = 0;

  if (strategy === 'all') {
    satisfied = matchedCanon.length === reqCanon.length && reqCanon.length > 0;
    rowTarget = reqCanon.reduce(function(s, c) { return s + (c.unit || 3); }, 0);
    rowEarned = matchedUnits;
    progress = reqCanon.length > 0 ? matchedCanon.length / reqCanon.length : 0;
  } else if (strategy === 'pick_n') {
    // For CUHK minors, a course-count row ("N courses") is always a floor,
    // since the section header states a unit total.  Allow surplus courses.
    if (!row.allow_surplus) row.allow_surplus = true;
    var n = row.n || 1;
    // Check all level constraints (use expanded for counting)
    var constraints = row.level_constraint;
    if (constraints && !Array.isArray(constraints)) constraints = [constraints];
    var lcr = checkAllLevelConstraints(matchedCanon, constraints, studentUnits);
    var lcOkPick = lcr.allOk;
    var strictPick = lcr.strictest;

    satisfied = matchedCanon.length >= n && lcOkPick;
    var effCount = 0;
    // Progress with bucket allocation from level constraints
    if (strictPick && n > 0) {
      var hasPickUnits = strictPick.lc.min_units_needed;
      var hasPickCourses = strictPick.lc.min_courses_needed;
      if (hasPickCourses) {
        var lcNeed = strictPick.lc.min_courses_needed;
        var freeNeed = Math.max(0, n - lcNeed);
        var lcGot = Math.min(strictPick.lv.count, lcNeed);
        var overflow = Math.max(0, strictPick.lv.count - lcNeed);
        var freePool = Math.max(0, matchedCanon.length - strictPick.lv.count) + overflow;
        var freeGot = Math.min(freePool, freeNeed);
        progress = (lcGot + freeGot) / n;
        effCount = lcGot + freeGot;
      } else if (hasPickUnits) {
        // Units-based constraint for pick_n (e.g. "4 courses, at least 6 units at 3000+")
        var avgU = row.pick_n_avg_unit || 3;
        if (!row.pick_n_avg_unit) {
          var puTotal = 0, puCount = 0;
          for (var i = 0; i < reqCanon.length; i++) {
            var u2 = reqCanon[i].unit || 3;
            if (u2 > 0) { puTotal += u2; puCount++; }
          }
          avgU = puCount > 0 ? puTotal / puCount : 3;
        }
        var lcNeedUnits = strictPick.lc.min_units_needed;
        var lcNeedCourses = Math.ceil(lcNeedUnits / avgU);
        var freeNeedPick = Math.max(0, n - lcNeedCourses);
        var lcGotPick = Math.min(strictPick.lv.count, lcNeedCourses);
        var overflowPick = Math.max(0, strictPick.lv.count - lcNeedCourses);
        var freePoolPick = Math.max(0, matchedCanon.length - strictPick.lv.count) + overflowPick;
        var freeGotPick = Math.min(freePoolPick, freeNeedPick);
        progress = (lcGotPick + freeGotPick) / n;
        effCount = lcGotPick + freeGotPick;
      } else {
        progress = Math.min(matchedCanon.length, n) / n;
        effCount = progress * n;
      }
    } else {
      progress = Math.min(matchedCanon.length, n) / n;
      effCount = progress * n;
    }
    // Use precomputed mode unit from data (consistent with section target)
    var avgU = row.pick_n_avg_unit || 3;
    if (!row.pick_n_avg_unit) {
      var puTotal = 0, puCount = 0;
      for (var i = 0; i < reqCanon.length; i++) {
        var u = reqCanon[i].unit || 3;
        if (u > 0) { puTotal += u; puCount++; }
      }
      avgU = puCount > 0 ? puTotal / puCount : 3;
    }
    rowTarget = n * avgU;
    // Use bucket allocation for earned if level constraint active
    if (strictPick && strictPick.lc.min_courses_needed) {
      rowEarned = (row.allow_surplus && lcOkPick) ? Math.max((lcGot + freeGot) * avgU, matchedUnits) : (lcGot + freeGot) * avgU;
    } else if (strictPick && strictPick.lc.min_units_needed) {
      // Units-based earned for pick_n (capped by freeNeedPick capacity)
      var lcUnitsGot = Math.min(strictPick.lv.units, strictPick.lc.min_units_needed);
      var freeCap = Math.max(0, (freeNeedPick || 0) * avgU);
      var freeUnitsEarned = Math.max(0, Math.min(matchedUnits - strictPick.lv.units, freeCap));
      rowEarned = (row.allow_surplus && lcOkPick) ? Math.max(lcUnitsGot + freeUnitsEarned, matchedUnits) : lcUnitsGot + freeUnitsEarned;
    } else {
      rowEarned = row.allow_surplus ? matchedUnits : Math.min(matchedCanon.length, n) * avgU;
    }
  } else if (strategy === 'units') {
    var needed = row.units_needed || 0;
    var neededMax = row.units_needed_max || needed; // use max for consumption cap
    var constraints2 = row.level_constraint;
    if (constraints2 && !Array.isArray(constraints2)) constraints2 = [constraints2];
    var lcr2 = checkAllLevelConstraints(matchedCanon, constraints2, studentUnits);
    var lcOk = lcr2.allOk;
    var strictU = lcr2.strictest;
    var greedySum = 0;

    // Bucket allocation across ALL level constraints (not just strictest)
    var hasAnyLC = lcr2.results && lcr2.results.length > 0;
    if (hasAnyLC) {
      // Sum level needs and matched across all constraints
      var totalLvlUnits = 0, totalLvlCourses = 0;
      var matchedLvlUnits = 0, matchedLvlCourses = 0;
      for (var li = 0; li < lcr2.results.length; li++) {
        var r2 = lcr2.results[li];
        if (r2.lc.min_units_needed) {
          totalLvlUnits += r2.lc.min_units_needed;
          matchedLvlUnits += Math.min(r2.lv.units, r2.lc.min_units_needed);
        }
        if (r2.lc.min_courses_needed) {
          totalLvlCourses += r2.lc.min_courses_needed;
          matchedLvlCourses += Math.min(r2.lv.count, r2.lc.min_courses_needed);
        }
      }
      var hasULC = totalLvlUnits > 0 || totalLvlCourses > 0;
      if (hasULC && needed > 0) {
        var estUnit = matchedUnits / Math.max(1, matchedCanon.length);
        if (row.pick_n_avg_unit) estUnit = row.pick_n_avg_unit;
        // Level bucket: sum of all constraint requirements (in units)
        var lvlNeeded = totalLvlUnits + totalLvlCourses * estUnit;
        var freeNeeded = Math.max(0, needed - lvlNeeded);
        // Level matched: sum of all constraint matches (in units)
        var lvlMatched = matchedLvlUnits + matchedLvlCourses * estUnit;
        var overflow = Math.max(0, lvlMatched - lvlNeeded);
        var freePool = Math.max(0, matchedUnits - lvlMatched) + overflow;
        var freeMatched = Math.min(freePool, freeNeeded);
        progress = (lvlMatched + freeMatched) / needed;
        greedySum = lvlMatched + freeMatched;
      } else {
        // Greedy: accumulate highest-unit courses first, allow last to overflow
        greedySum = 0;
        for (var gi = 0; gi < matchedCanon.length; gi++) {
          var canon = matchedCanon[gi];
          var alreadyGC = excludeCanon ? (excludeCanon[canon] || 0) : 0;
          var rawGC = studentRawUnits[canon] || studentUnits[canon] || 3;
          var gu = Math.min(rawGC - alreadyGC, studentUnits[canon] || 3);
          if (gu <= 0) continue;
          greedySum += gu;
          if (greedySum >= neededMax) break;
        }
        progress = needed > 0 ? Math.min(greedySum, needed) / needed : 0;
      }
    } else {
      // No level constraints — simple greedy
      greedySum = 0;
      for (var gi = 0; gi < matchedCanon.length; gi++) {
        var canon = matchedCanon[gi];
        var alreadyGC = excludeCanon ? (excludeCanon[canon] || 0) : 0;
        var rawGC = studentRawUnits[canon] || studentUnits[canon] || 3;
        var gu = Math.min(rawGC - alreadyGC, studentUnits[canon] || 3);
        if (gu <= 0) continue;
        greedySum += gu;
        if (greedySum >= neededMax) break;
      }
      progress = needed > 0 ? Math.min(greedySum, needed) / needed : 0;
    }
    satisfied = matchedUnits >= needed && lcOk;
    rowTarget = needed;
    rowEarned = Math.min(greedySum || 0, neededMax);
    // If level constraints exist, earned is capped by summed level contribution
    if (lcr2.results && lcr2.results.length > 0) {
      var estUnit2 = matchedUnits / Math.max(1, matchedCanon.length);
      if (row.pick_n_avg_unit) estUnit2 = row.pick_n_avg_unit;
      // Sum level needed and matched across all constraints
      var sumLNeed = 0, sumLGot = 0;
      for (var li2 = 0; li2 < lcr2.results.length; li2++) {
        var r3 = lcr2.results[li2];
        if (r3.lc.min_units_needed) {
          sumLNeed += r3.lc.min_units_needed;
          sumLGot += Math.min(r3.lv.units, r3.lc.min_units_needed);
        }
        if (r3.lc.min_courses_needed) {
          sumLNeed += r3.lc.min_courses_needed * estUnit2;
          sumLGot += Math.min(r3.lv.count * estUnit2, r3.lc.min_courses_needed * estUnit2);
        }
      }
      if (sumLNeed > 0) {
        var fNeed2 = Math.max(0, needed - sumLNeed);
        var ovf2 = Math.max(0, sumLGot - sumLNeed);
        var fPool2 = Math.max(0, matchedUnits - sumLGot) + ovf2;
        var fGot2 = Math.min(fPool2, fNeed2);
        rowEarned = Math.min(rowEarned, sumLGot + fGot2);
      }
    }
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
        var consumedAlready2 = excludeCanon ? (excludeCanon[gCanon[ci]] || 0) : 0;
        var totalAvail2 = (studentRawUnits[gCanon[ci]] || studentUnits[gCanon[ci]] || 3);
        if (studentCanonSet[gCanon[ci]] && consumedAlready2 < totalAvail2) {
          gMatched.push(gCanon[ci]);
          gUnits += Math.min(totalAvail2 - consumedAlready2, (studentUnits[gCanon[ci]] || 3));
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
    rowTarget = row.units_needed || bestTarget; // use precomputed min target
    rowEarned = bestProgress * rowTarget;
  } else if (strategy === 'any') {
    satisfied = false;
    progress = 0;
    rowTarget = 0;
    rowEarned = 0;
  }

  // Determine which matched courses were actually consumed (not surplus)
  var consumedCanon = [];
  if (strategy === 'all') {
    consumedCanon = matchedCanon.slice();
  } else if (strategy === 'units') {
    var cumSum = 0;
    for (var ci = 0; ci < matchedCanon.length; ci++) {
      var canon = matchedCanon[ci];
      var alreadyCC = excludeCanon ? (excludeCanon[canon] || 0) : 0;
      var rawCC = studentRawUnits[canon] || studentUnits[canon] || 3;
      var guC = Math.min(rawCC - alreadyCC, studentUnits[canon] || 3);
      if (guC <= 0) continue;
      consumedCanon.push(canon);
      cumSum += guC;
      if (cumSum >= rowEarned) break;
    }
  } else if (strategy === 'pick_n') {
    var limit = Math.min(matchedCanon.length, row.n || 1);
    if (row.level_constraint && effCount > 0 && effCount < limit) { limit = effCount; }
    if (row.allow_surplus && (typeof lcOkPick === 'undefined' ? true : lcOkPick)) {
      consumedCanon = matchedCanon.slice(); // floor: all matched count (level OK or no LC)
    } else if (row.level_constraint && strictPick && limit > 0) {
      // Prioritize level-matching courses for consumedCanon
      var lvlCourses = [], freeCourses = [];
      for (var ci = 0; ci < matchedCanon.length; ci++) {
        var canon = matchedCanon[ci];
        var meets = true;
        if (strictPick.lc.min_level || 0 > 0) {
          meets = courseLevel(canon) >= (strictPick.lc.min_level || 0);
          if (strictPick.lc.max_level != null) meets = meets && courseLevel(canon) <= strictPick.lc.max_level;
        }
        if (meets) lvlCourses.push(canon); else freeCourses.push(canon);
      }
      var lcTakePick = Math.min(lvlCourses.length, (lcGotPick !== undefined ? lcGotPick : lcGot) || 0);
      // Remaining level courses can fill the free bucket — sort by unit desc
      var remainingLvl = lvlCourses.slice(lcTakePick);
      var freePoolAll = remainingLvl.concat(freeCourses);
      freePoolAll.sort(function(a, b) { return (studentUnits[b] || 3) - (studentUnits[a] || 3); });
      var freeTakePick = Math.min(freePoolAll.length, limit - lcTakePick);
      for (var ci = 0; ci < lcTakePick; ci++) consumedCanon.push(lvlCourses[ci]);
      for (var ci = 0; ci < freeTakePick; ci++) consumedCanon.push(freePoolAll[ci]);
    } else {
      for (var ci = 0; ci < limit; ci++) consumedCanon.push(matchedCanon[ci]);
    }
  } else if (strategy === 'or_group') {
    consumedCanon = matchedCanon.slice();
  }

  var result = {
    text: row.text,
    strategy: strategy,
    codes: row.codes,
    dedup_count: row.dedup_count || row.codes.length,
    or_groups: row.or_groups,
    matched: matchedCanon,
    consumed: consumedCanon,
    matchedUnits: matchedUnits,
    matchedExact: matchedExact,
    matchedEquiv: matchedEquiv,
    hasTrueEquivMatch: hasTrueEquivMatch,
    satisfied: satisfied,
    progress: progress,
    rowTarget: rowTarget,
    rowEarned: rowEarned,
    rawStudentUnits: rawStudentUnitsTotal,
    n: row.n,
    allow_surplus: row.allow_surplus || false,
    effCount: effCount,
    units_needed: row.units_needed,
    units_needed_max: row.units_needed_max,
    level_constraint: row.level_constraint,
    eqLost: Math.max(0, rawStudentUnitsTotal - matchedUnits),
    levelLost: 0,
    sectionLost: 0,
    subjectLost: 0,
    bucketInfo: null,
    bucketOk: true,
    subjectMin: null,
    actualSubj: 0
  };

  // Compute level vs section cap losses
  if (strategy === 'units' || strategy === 'pick_n') {
    var noLcEarned = rowEarned;
    var lcAllOk = (strategy === 'pick_n' && lcOkPick) || (strategy === 'units' && lcOk) || false;
    if (strategy === 'units') {
      noLcEarned = matchedUnits;
    } else if (strategy === 'pick_n') {
      noLcEarned = matchedUnits;
    }
    if (row.level_constraint && !lcAllOk && noLcEarned > rowEarned) {
      result.levelLost = noLcEarned - rowEarned;
    }
    result.sectionLost = Math.max(0, matchedUnits - rowEarned - result.levelLost);
  }

  // ── Subject constraints ───────────────────────────────────────────────
  // 5a. Subject area minimums (e.g., "at least 3 subject areas")
  if (row.subject_min && matchedCanon.length > 0) {
    var subjSet = {};
    // Count subject areas from the student's ORIGINAL course prefixes
    // (not canonical — IERG and ESTR are separate areas at CUHK)
    for (var sc in studentCanonSet._exact) {
      if (studentCanonSet._exact[sc]) {
        var scCanon = canonFn(sc);
        // Check if this student course matches any row requirement code
        for (var ci = 0; ci < row.codes.length; ci++) {
          if (canonFn(row.codes[ci].code) === scCanon) {
            subjSet[sc.split(' ')[0]] = true;
            break;
          }
        }
      }
    }
    var distinctSubj = Object.keys(subjSet).length;
    if (distinctSubj < row.subject_min) {
      result.satisfied = false;
      result.progress = Math.min(result.progress, distinctSubj / row.subject_min);
      // Reserve one course worth per missing subject area
      var avgCourseU = matchedUnits / Math.max(1, matchedCanon.length);
      var reserved = (row.subject_min - distinctSubj) * avgCourseU;
      result.rowEarned = Math.min(result.rowEarned || 0, Math.max(0, (rowTarget || matchedUnits) - reserved));
    }
    result.subjectMin = row.subject_min;
    result.actualSubj = distinctSubj;
  }

  // 5b. Subject buckets (e.g., "6 units GDRS, 6 units non-GDRS")
  if (row.subject_buckets) {
    var allBucketsOk = true;
    var bProgTotal = 0;
    var totalShortfall = 0;
    var maxTotalExcess = 0;
    var avgUnit = matchedUnits / Math.max(1, matchedCanon.length);
    if (row.pick_n_avg_unit) avgUnit = row.pick_n_avg_unit;
    var bucketInfo = [];
    for (var bi = 0; bi < row.subject_buckets.length; bi++) {
      var b = row.subject_buckets[bi];
      var bPref = b.prefix || '';
      var isNeg = bPref.charAt(0) === '!';
      var actualPref = isNeg ? bPref.substring(1) : bPref;
      var bUnits = 0, bCourses = 0;
      if (b.code_list) {
        for (var ci = 0; ci < matchedCanon.length; ci++) {
          var canon = matchedCanon[ci];
          var isMatch = false;
          for (var sci in studentCanonSet._exact) {
            if (!studentCanonSet._exact.hasOwnProperty(sci) || sci === '__proto__') continue;
            if (canonFn(sci) !== canon) continue;
            var parts2 = sci.split(' ');
            var numSuffix2 = parts2.length > 1 ? parts2[1] : '';
            if (b.code_list.indexOf(numSuffix2) !== -1) { isMatch = true; break; }
          }
          if (isMatch) {
            bUnits += (studentUnits[canon] || 3);
            bCourses++;
          }
        }
      } else {
        for (var ci = 0; ci < matchedCanon.length; ci++) {
          var mp = matchedCanon[ci].split(' ')[0];
          if (isNeg ? (mp !== actualPref) : (mp === actualPref)) {
            bUnits += (studentUnits[matchedCanon[ci]] || 3);
            bCourses++;
          }
        }
      }
      var bucketOk = true;
      if (b.min_units && bUnits < b.min_units) {
        bucketOk = false;
        totalShortfall += b.min_units - bUnits;
      }
      if (b.max_units && bUnits > b.max_units) {
        bucketOk = false;
        maxTotalExcess += bUnits - b.max_units;
      }
      if (b.min_courses && bCourses < b.min_courses) {
        bucketOk = false;
        totalShortfall += (b.min_courses - bCourses) * avgUnit;
      }
      allBucketsOk = allBucketsOk && bucketOk;
      var bp = 1;
      if (b.min_units && b.min_units > 0) bp = Math.min(bUnits, b.min_units) / b.min_units;
      if (b.min_courses && b.min_courses > 0) bp = Math.min(bp, bCourses / b.min_courses);
      bProgTotal += bp;
      bucketInfo.push({prefix: actualPref, isNeg: isNeg, units: bUnits, courses: bCourses, min_units: b.min_units, min_courses: b.min_courses, max_units: b.max_units, code_list: b.code_list, label: b.label});
    }
    if (!allBucketsOk) result.satisfied = false;
    result.progress = Math.min(result.progress, bProgTotal / row.subject_buckets.length);
    // Bucket-limited earned: start from matched, deduct max excess (from capped courses),
    // then apply min shortfalls against the row target
    var bucketEarned = Math.min(Math.max(0, matchedUnits - maxTotalExcess), Math.max(0, (rowTarget || matchedUnits) - totalShortfall));
    result.bucketInfo = bucketInfo;
    result.bucketOk = allBucketsOk;
    result._bucketEarned = bucketEarned;
    result._preBucketRowEarned = rowEarned;
  }

  // 5c. Multi-level constraints progress (use worst across all)
  if (row.level_constraint) {
    var mlcList = Array.isArray(row.level_constraint) ? row.level_constraint : [row.level_constraint];
    if (mlcList.length > 1) {
      var mlcr = checkAllLevelConstraints(matchedCanon, mlcList, studentUnits);
      result.progress = Math.min(result.progress, mlcr.minProgress || 1);
    }
  }

  return result;
}

function scoreMinor(minorData, studentCourses, courseIndex) {
  var canonFn = makeCanonicalizer(minorData.eq_norm);

  // Expand and-groups: if student has all courses in a multi-course equivalence,
  // add the target canonical as a synthetic course with combined units
  if (minorData.and_eq_groups && minorData.and_eq_groups.length) {
    for (var ai = 0; ai < minorData.and_eq_groups.length; ai++) {
      var ag = minorData.and_eq_groups[ai];
      var allFound = true;
      var sumUnit = 0;
      for (var gi = 0; gi < ag.courses.length; gi++) {
        var found = false;
        for (var si = 0; si < studentCourses.length; si++) {
          if (studentCourses[si].code === ag.courses[gi]) { found = true; sumUnit += studentCourses[si].unit || (courseIndex[ag.courses[gi]] && courseIndex[ag.courses[gi]].unit) || 0; break; }
        }
        if (!found) { allFound = false; break; }
      }
      if (allFound) {
        var reqUnit = (courseIndex[ag.canon] && courseIndex[ag.canon].unit) || 0;
        var cappedUnit = Math.min(ag.total_units || sumUnit || 4, reqUnit || 999);
        studentCourses.push({code: ag.canon, unit: cappedUnit, _and_group: true});
      }
    }
  }

  // Waiver rules: add synthetic courses for waiver, track credit_units
  var waiverSet = {}; // waived course codes that are active
  var waiverActive = false;
  var extraCreditTotal = 0;
  var sectionCredit = {};
  var sectionTriggers = {}; // section_idx -> [trigger_codes] for credit rules
  if (minorData.waiver_rules && minorData.waiver_rules.length) {
    for (var wi = 0; wi < minorData.waiver_rules.length; wi++) {
      var wr = minorData.waiver_rules[wi];
      var hasTrigger = false;
      for (var si = 0; si < studentCourses.length; si++) {
        if (studentCourses[si].code === wr.trigger) { hasTrigger = true; break; }
      }
      if (!hasTrigger) continue;
      // Credit-only rules (summer intensive course credit)
      if (wr.credit_units > 0) {
        extraCreditTotal += wr.credit_units;
        var cs = wr.credit_section || 1;
        sectionCredit[cs] = (sectionCredit[cs] || 0) + wr.credit_units;
        if (!sectionTriggers[cs]) sectionTriggers[cs] = [];
        sectionTriggers[cs].push(wr.trigger);
        continue;
      }
      // Standard waiver rules
      var wUnit = (courseIndex[wr.waive] && courseIndex[wr.waive].unit) || 3;
      studentCourses.push({code: wr.waive, unit: wUnit, _waived: true});
      waiverSet[wr.waive] = true;
      waiverActive = true;
    }
  }

  // Build student canonical set and unit map
  var studentCanonSet = {_exact: {}};
  var studentUnits = {};
  var studentUnitList = {};  // individual course units per canonical, sorted desc
  var studentUnitIdx = {};   // how many courses consumed so far per canonical  
  var studentRawUnits = {};  // total raw units per canonical (for eq warning)
  for (var i = 0; i < studentCourses.length; i++) {
    var c = studentCourses[i];
    var canon = canonFn(c.code);
    studentCanonSet[canon] = true;
    studentCanonSet._exact[c.code] = true;
    if (c._waived) studentCanonSet._waived = studentCanonSet._waived || {};
    if (c._waived) studentCanonSet._waived[canon] = true;
    var infoUnit = (courseIndex[c.code] && courseIndex[c.code].unit) || 0;
    var u = Math.max(c.unit, infoUnit, 0) || 3;
    if (!studentUnitList[canon]) studentUnitList[canon] = [];
    studentUnitList[canon].push(u);
    studentUnits[canon] = Math.max(studentUnits[canon] || 0, u);
    studentRawUnits[canon] = (studentRawUnits[canon] || 0) + u;
  }
  for (var key in studentUnitList) {
    studentUnitList[key].sort(function(a,b){return b-a;});
    studentUnitIdx[key] = 0;
  }

  var sections = [];
  var totalTarget = 0;
  var totalEarned = 0;
  var usedCanonSet = {}; // track units consumed by canonical
  var usedOriginalCodes = {}; // track which original codes were assigned to rows

  // Compute global level threshold for sorting preference
  var globalMinLevel = 0;
  var glcForSort = minorData.global_level_constraint;
  if (glcForSort) {
    var glcSortList = Array.isArray(glcForSort) ? glcForSort : [glcForSort];
    for (var gli = 0; gli < glcSortList.length; gli++) {
      if (glcSortList[gli].min_level && (!globalMinLevel || glcSortList[gli].min_level < globalMinLevel)) {
        globalMinLevel = glcSortList[gli].min_level;
      }
    }
  }

  for (var si = 0; si < minorData.sections.length; si++) {
    var sec = minorData.sections[si];
    var secTarget = sec.target_units || 0;
    var secEarned = 0;
    var rows = [];

    for (var ri = 0; ri < sec.rows.length; ri++) {
      var rowData = sec.rows[ri];
      // When section has a unit range, let rows consume up to the section max
      if (sec.target_units_max && sec.target_units_max > (rowData.units_needed || 0)) {
        if (!rowData.units_needed_max) rowData.units_needed_max = sec.target_units_max;
      }
      var exclude = rowData.cross_row_exclude ? usedCanonSet : null;
      // Also exclude if any previous row consumed codes
      if (!exclude && Object.keys(usedCanonSet).length > 0) {
        exclude = usedCanonSet;
      }
      // Snapshot usedCanonSet before this row (to detect first-consumed vs spillover)
      var preUsed = {};
      for (var key in usedCanonSet) { preUsed[key] = usedCanonSet[key]; }
      var mr = matchRow(rowData, studentCanonSet, studentUnits, studentRawUnits, canonFn, exclude, studentUnitList, globalMinLevel);
      mr.preUsed = preUsed;
      mr.isNotesEquiv = false; // true when equivalence is from Explanatory Notes

      // Detect explanatory-notes equivalences: student has a notes_eq_codes
      // course that shares a canonical with a row code
      if (minorData.notes_eq_codes && minorData.notes_eq_codes.length) {
        var neqSet = minorData.notes_eq_codes;
        for (var sci in studentCanonSet._exact) {
          if (!studentCanonSet._exact.hasOwnProperty(sci) || sci === '__proto__') continue;
          if (neqSet.indexOf(sci) < 0) continue;
          var scCanon = canonFn(sci);
          for (var rci = 0; rci < rowData.codes.length; rci++) {
            if (scCanon === canonFn(rowData.codes[rci].code) && sci !== rowData.codes[rci].code) {
              mr.isNotesEquiv = true;
              break;
            }
          }
          if (mr.isNotesEquiv) break;
        }
        // Also check and-groups: if an and-group was expanded and its target
        // canon is in this row, mark as notes-equiv
        if (!mr.isNotesEquiv && minorData.and_eq_groups && minorData.and_eq_groups.length) {
          for (var agi = 0; agi < minorData.and_eq_groups.length; agi++) {
            var ag = minorData.and_eq_groups[agi];
            var allIn = true;
            for (var gc = 0; gc < ag.courses.length; gc++) {
              if (!studentCanonSet._exact[ag.courses[gc]]) { allIn = false; break; }
            }
            if (!allIn) continue;
            var agCanon = canonFn(ag.canon);
            for (var rci = 0; rci < rowData.codes.length; rci++) {
              if (agCanon === canonFn(rowData.codes[rci].code)) {
                mr.isNotesEquiv = true;
                break;
              }
            }
            if (mr.isNotesEquiv) break;
          }
        }
      }

      // Build consumedCodes: prefer exact-match codes the student actually took,
      // and among exact matches for the same canonical, pick the highest-unit code.
      mr.consumedCodes = [];
      var seenCanon = {};
      // First pass: collect candidate exact-match codes per canonical
      var candidates = {}; // canon -> {code, unit}
      for (var ci = 0; ci < rowData.codes.length; ci++) {
        var code = rowData.codes[ci].code;
        var canon = canonFn(code);
        if (mr.consumed && mr.consumed.indexOf(canon) !== -1 && !seenCanon[canon]) {
          if (!usedOriginalCodes[code] && studentCanonSet._exact && studentCanonSet._exact[code]) {
            var cfUnit = (courseIndex[code] && courseIndex[code].unit) || (studentUnits[canon] || 3);
            if (!candidates[canon] || cfUnit > candidates[canon].unit) {
              candidates[canon] = {code: code, unit: cfUnit};
            }
          }
        }
      }
      // Push the best candidate for each canonical
      for (var ci = 0; ci < rowData.codes.length; ci++) {
        var canon2 = canonFn(rowData.codes[ci].code);
        if (candidates[canon2] && !seenCanon[canon2]) {
          mr.consumedCodes.push(candidates[canon2].code);
          seenCanon[canon2] = true;
        }
      }
      // Fallback: for canonicals that didn't get a fresh code, pick first available
      var seenCanon2 = {};
      for (var ci2 = 0; ci2 < rowData.codes.length; ci2++) {
        var code2 = rowData.codes[ci2].code;
        var canon2 = canonFn(code2);
        if (mr.consumed && mr.consumed.indexOf(canon2) !== -1 && !seenCanon2[canon2]) {
          seenCanon2[canon2] = true;
          // Only add if this canonical isn't already covered by a consumedCode
          var alreadyCovered = false;
          for (var ck = 0; ck < mr.consumedCodes.length; ck++) {
            if (canonFn(mr.consumedCodes[ck]) === canon2) { alreadyCovered = true; break; }
          }
          if (!alreadyCovered && mr.consumedCodes.indexOf(code2) === -1) {
            mr.consumedCodes.push(code2);
          }
        }
      }
      for (var ci3 = 0; ci3 < mr.consumedCodes.length; ci3++) {
        usedOriginalCodes[mr.consumedCodes[ci3]] = true;
      }
      // Adjust rowEarned to match actual catalog units of consumed codes
      if (mr.strategy === 'units' || mr.strategy === 'pick_n') {
        var actualSum = 0;
        for (var ci4 = 0; ci4 < mr.consumedCodes.length; ci4++) {
          var cCode = mr.consumedCodes[ci4];
          var cInfo = courseIndex[cCode];
          actualSum += (cInfo && cInfo.unit) || (studentUnits[canonFn(cCode)] || 3);
        }
        // For pick_n with allow_surplus, don't cap at rowTarget — section cap handles budgets
        var cap = (mr.strategy === 'pick_n' && mr.allow_surplus) ? mr.rowEarned : (mr.units_needed_max || mr.rowTarget);
        mr.rowEarned = Math.min(actualSum || mr.rowEarned, cap, mr.rowEarned);
      }
      // Apply subject bucket cap after actualSum adjustment
      if (mr._bucketEarned != null && mr._bucketEarned < mr.rowEarned) {
        mr.subjectLost = Math.max(0, mr.rowEarned - mr._bucketEarned);
        mr.rowEarned = mr._bucketEarned;
      }
      // Rebuild consumed from ALL matched courses, preferring courses that
      // satisfy bucket minimums and deprioritizing limited-by-max courses
      if (mr.bucketInfo && mr.bucketInfo.length > 0) {
        var mustPreferred = [], neutral = [], postConsumed = [];
        var mustUnits = 0, neutralUnits = 0, postUnits = 0;
        var allMatched = mr.matched || mr.consumed;
        for (var ci = 0; ci < allMatched.length; ci++) {
          var canon = allMatched[ci];
          var mp = canon.split(' ')[0];
          var isPref = false, isLimited = false;
           for (var bi = 0; bi < mr.bucketInfo.length; bi++) {
             var b = mr.bucketInfo[bi];
             if (b.code_list) {
               var inList = false;
               for (var sci2 in studentCanonSet._exact) {
                 if (!studentCanonSet._exact.hasOwnProperty(sci2) || sci2 === '__proto__') continue;
                 if (canonFn(sci2) !== canon) continue;
                 var np2 = sci2.split(' ').length > 1 ? sci2.split(' ')[1] : '';
                 if (b.code_list.indexOf(np2) !== -1) { inList = true; break; }
               }
               if ((b.min_units || b.min_courses) && inList) isPref = true;
               if (b.max_units && inList) isLimited = true;
             } else {
               if (!b.isNeg && (b.min_units || b.min_courses) && mp === b.prefix) isPref = true;
               if (b.isNeg && (b.min_units || b.min_courses) && mp !== b.prefix) isPref = true;
               if (b.isNeg && b.max_units && mp !== b.prefix) isLimited = true;
               if (!b.isNeg && b.max_units && mp === b.prefix) isLimited = true;
             }
          }
          if (isLimited && !isPref) {
            postConsumed.push(canon); postUnits += (studentUnits[canon] || 3);
          } else if (isPref) {
            mustPreferred.push(canon); mustUnits += (studentUnits[canon] || 3);
          } else {
            neutral.push(canon); neutralUnits += (studentUnits[canon] || 3);
          }
        }
        // Combine: must-preferred first, then neutral, then limited up to earned
        var newConsumed2 = mustPreferred.slice().concat(neutral);
        var cumTotal = mustUnits + neutralUnits;
        for (var ci = 0; ci < postConsumed.length; ci++) {
          if (cumTotal >= mr.rowEarned) break;
          newConsumed2.push(postConsumed[ci]);
          cumTotal += (studentUnits[postConsumed[ci]] || 3);
        }
        mr.consumed = newConsumed2;
        // Rebuild consumedCodes to match the new consumedCanon
        // Prefer codes the student actually took (exact matches)
        var rebuiltCodes = [];
        var rebSeenCanon = {};
        for (var ci = 0; ci < rowData.codes.length; ci++) {
          var code = rowData.codes[ci].code;
          var canon = canonFn(code);
          if (mr.consumed.indexOf(canon) !== -1 && !rebSeenCanon[canon]) {
            if (studentCanonSet._exact && studentCanonSet._exact[code]) {
              rebuiltCodes.push(code);
              rebSeenCanon[canon] = true;
            }
          }
        }
        // Fallback: any code for remaining canonicals
        for (var ci = 0; ci < rowData.codes.length; ci++) {
          var code2 = rowData.codes[ci].code;
          var canon2 = canonFn(code2);
          if (mr.consumed.indexOf(canon2) !== -1 && !rebSeenCanon[canon2]) {
            rebuiltCodes.push(code2);
            rebSeenCanon[canon2] = true;
          }
        }
        mr.consumedCodes = rebuiltCodes;
      }
      secEarned += mr.rowEarned;
      rows.push(mr);
      // Track units consumed by canonical (allow spillover of remaining units)
      if (!mr.consumedUnits) mr.consumedUnits = {};
      // For pick_n with allow_surplus, only track up to the minimum n courses —
      // surplus courses remain available for later rows/sections.
      var trackLimit = mr.consumed.length;
      if (mr.strategy === 'pick_n' && mr.allow_surplus && mr.n) {
        trackLimit = Math.min(trackLimit, mr.n);
      }
      for (var mi = 0; mi < trackLimit; mi++) {
        var canon = mr.consumed[mi];
        var remaining = (studentRawUnits[canon] || studentUnits[canon] || 3) - (usedCanonSet[canon] || 0);
        var consumedNow = Math.min(remaining, studentUnits[canon] || 3);
        usedCanonSet[canon] = (usedCanonSet[canon] || 0) + consumedNow;
        mr.consumedUnits[canon] = (mr.consumedUnits[canon] || 0) + consumedNow;
      }
    }

    var secCap = (sec.target_units_max != null ? sec.target_units_max : secTarget) || secEarned + 1;
    secEarned = Math.min(secEarned, secCap); // cap at target (max when range present)
    // Enforce per-row minimums: if any row hasn't met its minimum, reduce section earned
    var missingMin = 0;
    for (var ri = 0; ri < rows.length; ri++) {
      var rMin = rows[ri].rowTarget || 0;
      if (rows[ri].rowEarned < rMin) {
        missingMin += rMin - rows[ri].rowEarned;
      }
    }
    if (missingMin > 0) {
      secEarned = Math.min(secEarned, Math.max(0, secTarget - missingMin));
    }
    totalTarget += secTarget;
    totalEarned += secEarned;

    // Reorder consumedCanon to prefer distinct subject areas (for subject_min)
    for (var ri = 0; ri < rows.length; ri++) {
      var row = rows[ri];
      if (row.subjectMin && row.matched && row.matched.length > 1) {
        // Rebuild from ALL matched courses, distinct prefixes first, then truncate to rowEarned
        var seenPref = {}, distinct = [], rest = [];
        for (var ci = 0; ci < row.matched.length; ci++) {
          var mp2 = row.matched[ci].split(' ')[0];
          if (!seenPref[mp2]) { seenPref[mp2] = true; distinct.push(row.matched[ci]); }
          else { rest.push(row.matched[ci]); }
        }
        var reorderedAll = distinct.concat(rest);
        var cumSubj = 0, newConsSubj = [];
        for (var ci = 0; ci < reorderedAll.length; ci++) {
          if (cumSubj >= row.rowEarned) break;
          cumSubj += (studentUnits[reorderedAll[ci]] || 3);
          newConsSubj.push(reorderedAll[ci]);
        }
        row.consumed = newConsSubj;
        // Also rebuild consumedCodes (one per canonical, prefer distinct prefixes)
        var newCodes = [];
        var seenCodeCanon = {};
        var usedPref = {};
        var rowCodesRef = sec.rows[ri].codes;
        // First pass: prefer codes with new prefixes
        for (var ci = 0; ci < rowCodesRef.length; ci++) {
          var code = rowCodesRef[ci].code;
          var canon = canonFn(code);
          if (newConsSubj.indexOf(canon) !== -1 && !seenCodeCanon[canon] && newCodes.indexOf(code) === -1) {
            if (!usedPref[code.split(' ')[0]]) {
              newCodes.push(code);
              seenCodeCanon[canon] = true;
              usedPref[code.split(' ')[0]] = true;
            }
          }
        }
        // Fallback: remaining canonicals get any code
        for (var ci = 0; ci < rowCodesRef.length; ci++) {
          var code2 = rowCodesRef[ci].code;
          var canon2 = canonFn(code2);
          if (newConsSubj.indexOf(canon2) !== -1 && !seenCodeCanon[canon2] && newCodes.indexOf(code2) === -1) {
            newCodes.push(code2);
            seenCodeCanon[canon2] = true;
          }
        }
        row.consumedCodes = newCodes;
      }
    }

    // Finalize consumedCanon: truncate each row to match its earned units
    for (var ri = 0; ri < rows.length; ri++) {
      var row = rows[ri];
      var cumRow = 0;
      var newConsRows = [];
      for (var ci = 0; ci < (row.consumed || []).length; ci++) {
        if (cumRow >= row.rowEarned) break;
        var u = studentUnits[row.consumed[ci]] || 3;
        cumRow += u;
        newConsRows.push(row.consumed[ci]);
      }
      row.consumed = newConsRows;
      // Also rebuild consumedCodes to match
      var newConsCodes = [];
      for (var ci = 0; ci < (row.consumedCodes || []).length; ci++) {
        var code = row.consumedCodes[ci];
        var canon = canonFn(code);
        if (newConsRows.indexOf(canon) !== -1) newConsCodes.push(code);
      }
      row.consumedCodes = newConsCodes;
    }

    sections.push({
      label: sec.label,
      target_units: secTarget,
      target_units_max: sec.target_units_max,
      earned_units: secEarned,
      progress: secTarget > 0 ? secEarned / secTarget : 0,
      rows: rows
    });
  }

  var overall = totalTarget > 0 ? totalEarned / totalTarget : 0;
  var globalLevelLost = 0;
  var glNote = '';

  // Use description-based total as authoritative overall target
  if (minorData.total_units && minorData.total_units > 0) {
    totalTarget = minorData.total_units;
    totalEarned = Math.min(totalEarned, totalTarget);
    overall = totalTarget > 0 ? totalEarned / totalTarget : 0;
  }

  // Cap overall progress with global level constraint from description
  var glc = minorData.global_level_constraint;
  if (glc && totalTarget > 0) {
    var glcList = Array.isArray(glc) ? glc : [glc];
    // Build set of eligible codes for this minor (filter out irrelevant courses)
    var eligibleCanon = {};
    for (var si = 0; si < minorData.sections.length; si++) {
      for (var ri = 0; ri < minorData.sections[si].rows.length; ri++) {
        var rowCodes = minorData.sections[si].rows[ri].codes;
        for (var ci = 0; ci < rowCodes.length; ci++) {
          eligibleCanon[canonFn(rowCodes[ci].code)] = true;
        }
      }
    }
    // Count student courses at required levels (dedup by canonical)
    var allStudentCanon = [];
    var allCanonSeen = {};
    for (var i = 0; i < studentCourses.length; i++) {
      var sc = canonFn(studentCourses[i].code);
      if (eligibleCanon[sc] && !allCanonSeen[sc]) {
        allStudentCanon.push(sc);
        allCanonSeen[sc] = true;
      }
    }
    // Use the strictest global constraint
    var strictGLC = null;
    var strictLv = null;
    for (var i = 0; i < glcList.length; i++) {
      var lv = countLevelMatches(allStudentCanon, glcList[i], studentUnits);
      if (!strictGLC || (glcList[i].min_level || 0) > (strictGLC.min_level || 0)) {
        strictGLC = glcList[i];
        strictLv = lv;
      }
    }
    if (strictGLC && strictGLC.min_units_needed && totalTarget > 0) {
      var glNeed = strictGLC.min_units_needed;
      var glFree = Math.max(0, totalTarget - glNeed);
      var glGot = Math.min(strictLv.units, glNeed);
      var glOvf = Math.max(0, strictLv.units - glNeed);
      // total eligible student units at any level (dedup by canonical)
      var allStudentUnits = 0;
      var allUnitsSeen = {};
      for (var i = 0; i < studentCourses.length; i++) {
        var sc = canonFn(studentCourses[i].code);
        if (eligibleCanon[sc] && !allUnitsSeen[sc]) {
          allStudentUnits += (studentUnits[sc] || 3);
          allUnitsSeen[sc] = true;
        }
      }
      var glFreePool = Math.max(0, allStudentUnits - strictLv.units) + glOvf;
      var glFreeGot = Math.min(glFreePool, glFree);
      var cappedEarned = glGot + glFreeGot;
      // Global constraint only produces loss when the level bucket is unfilled.
      // If the student meets the level requirement, section-level progress
      // already handles the total-unit shortfall — no additional cap needed.
      globalLevelLost = Math.max(0, totalEarned - cappedEarned);
      if (glGot >= glNeed) globalLevelLost = 0;
      // Track why: level bucket not full, free bucket limited, or both
      glNote = '';
      if (globalLevelLost > 0) {
        var lvlShort = Math.max(0, glNeed - glGot);
        var freeShort = Math.max(0, glFree - glFreeGot);
        if (lvlShort > 0 && freeShort > 0) glNote = ' (insufficient level courses + total units)';
        else if (lvlShort > 0) glNote = ' (not enough courses at the required level)';
        else if (freeShort > 0) glNote = ' (not enough total eligible units)';
      }
      overall = Math.min(overall, cappedEarned / totalTarget);
      totalEarned = Math.min(totalEarned, cappedEarned);
    }
  }

  // Note: global-level constraint only affects overall progress,
  // not individual section headings.

  // Faculty cap: store excess for warning display
  var globalFacLost = 0;

  // Faculty cap: if minor has faculty_caps, cap same-faculty non-excluded units
  if (minorData.faculty_caps && minorData.faculty_caps.max_units && minorData.faculty_caps.groups) {
    var fcData = minorData.faculty_caps;
    var facExclude = fcData.exclude_prefix || '';
    var facGroups = fcData.groups;
    var facCapMax = fcData.max_units;
    var facUnitMap = {}; // faculty -> units
    // Build reverse prefix->faculty map
    var prefixToFac = {};
    for (var fg in facGroups) {
      if (!facGroups.hasOwnProperty(fg)) continue;
      var prefixes = facGroups[fg];
      for (var pi = 0; pi < prefixes.length; pi++) {
        prefixToFac[prefixes[pi]] = fg;
      }
    }
    // Sum consumed units per faculty across all rows
    for (var si = 0; si < sections.length; si++) {
      for (var ri = 0; ri < sections[si].rows.length; ri++) {
        var facRow = sections[si].rows[ri];
        var facConsumed = facRow.consumedCodes || [];
        for (var fci = 0; fci < facConsumed.length; fci++) {
          var fcCode = facConsumed[fci];
          var fcPref = fcCode.split(' ')[0];
          if (fcPref === facExclude) continue;
          var fcFaculty = prefixToFac[fcPref];
          if (!fcFaculty) continue;
          var fcCanon = canonFn(fcCode);
          facUnitMap[fcFaculty] = (facUnitMap[fcFaculty] || 0) + (studentUnits[fcCanon] || 3);
        }
      }
    }
    // Cap per-faculty and compute overage. Total progression = sum of min(per-fac, cap) + excluded
    var facOver = 0;
    for (var fk in facUnitMap) {
      if (facUnitMap.hasOwnProperty(fk) && facUnitMap[fk] > facCapMax) {
        facOver += facUnitMap[fk] - facCapMax;
      }
    }
    if (facOver > 0) {
      globalFacLost = facOver;
      var cappedTotal = 0;
      for (var fk2 in facUnitMap) {
        if (facUnitMap.hasOwnProperty(fk2)) cappedTotal += Math.min(facUnitMap[fk2], facCapMax);
      }
      for (var si = 0; si < sections.length; si++) {
        for (var ri = 0; ri < sections[si].rows.length; ri++) {
          var fcr = sections[si].rows[ri];
          var fcc = fcr.consumedCodes || [];
          for (var fci2 = 0; fci2 < fcc.length; fci2++) {
            if (fcc[fci2].split(' ')[0] === facExclude) {
              cappedTotal += (studentUnits[canonFn(fcc[fci2])] || 3);
            }
          }
        }
      }
      totalEarned = Math.min(totalEarned, Math.max(0, cappedTotal));
      overall = totalTarget > 0 ? totalEarned / totalTarget : 0;
    }
  }

  // Waiver adjustment: synthetic waived courses contribute to matching
  // but their earned contribution is held back unless replacement is taken.
  var waiverSatisfied = false; // true if ALL waived courses are satisfied
  var waiverSatisfiedSet = {}; // per-course satisfied flags
  if (waiverActive) {
    var waivedUnitSum = 0;
    var sectWaived = {};
    for (var si = 0; si < sections.length; si++) {
      sectWaived[si] = 0;
      for (var ri = 0; ri < sections[si].rows.length; ri++) {
        var wRow = sections[si].rows[ri];
        wRow.waivedEarned = 0;
        if (studentCanonSet._waived) {
          for (var wci = 0; wci < wRow.codes.length; wci++) {
            var wCanon = canonFn(wRow.codes[wci].code);
            if (studentCanonSet._waived[wCanon]) {
              var wu = (studentUnits[wCanon] || 3);
              wRow.waivedEarned += wu;
              waivedUnitSum += wu;
              sectWaived[si] += wu;
            }
          }
        }
      }
    }
    // If total earned (excluding waived) + waived units covers the target,
    // waived courses are satisfied: add their units to earned
    var earnedNoWaive = Math.max(0, totalEarned - waivedUnitSum);
    // Surplus: raw row contributions that exceed section caps
    var surplusUnits = 0;
    for (var si2 = 0; si2 < sections.length; si2++) {
      var sec2 = sections[si2];
      var rowRaw = 0;
      for (var ri2 = 0; ri2 < sec2.rows.length; ri2++) {
        rowRaw += sec2.rows[ri2].rowEarned;
      }
      if (rowRaw > sec2.earned_units) surplusUnits += rowRaw - sec2.earned_units;
      for (var ri2 = 0; ri2 < sec2.rows.length; ri2++) {
        var sr = sec2.rows[ri2];
        if (sr.matched && sr.consumed && sr.matched.length > sr.consumed.length) {
          surplusUnits += (sr.matched.length - sr.consumed.length) * (sr.pick_n_avg_unit || 3);
        }
      }
    }
    // Apply surplus to waived courses one by one (in order of row codes)
    var remainingSurplus = surplusUnits + (earnedNoWaive >= totalTarget ? 999 : 0);
    var allSatisfied = true;
    for (var si = 0; si < sections.length; si++) {
      for (var ri = 0; ri < sections[si].rows.length; ri++) {
        var wr = sections[si].rows[ri];
        for (var wci = 0; wci < wr.codes.length; wci++) {
          var wcCode = wr.codes[wci].code;
          var wCanon = canonFn(wcCode);
          if (studentCanonSet._waived && studentCanonSet._waived[wCanon]) {
            var wu = (courseIndex[wcCode] && courseIndex[wcCode].unit) || 3;
            if (remainingSurplus >= wu) {
              remainingSurplus -= wu;
              waiverSatisfiedSet[wcCode] = true;
            } else {
              allSatisfied = false;
            }
          }
        }
      }
    }
    waiverSatisfied = allSatisfied;
    if (!waiverSatisfied) {
      // Only subtract unsatisfied waived units
      for (var si = 0; si < sections.length; si++) {
        var unsatSec = 0;
        for (var ri = 0; ri < sections[si].rows.length; ri++) {
          var wr = sections[si].rows[ri];
          var unsatRow = 0;
          for (var wci = 0; wci < wr.codes.length; wci++) {
            var wcCode = wr.codes[wci].code;
            var wCanon = canonFn(wcCode);
            if (studentCanonSet._waived && studentCanonSet._waived[wCanon] && !waiverSatisfiedSet[wcCode]) {
              var wu = (studentUnits[wCanon] || 3);
              unsatRow += wu;
              unsatSec += wu;
            }
          }
          if (unsatRow > 0) wr.rowEarned = Math.max(0, wr.rowEarned - unsatRow);
        }
        if (unsatSec > 0) {
          sections[si].earned_units = Math.max(0, sections[si].earned_units - unsatSec);
          sections[si].progress = sections[si].target_units > 0 ? sections[si].earned_units / sections[si].target_units : 0;
        }
      }
    }
  }

  // Add extra credit from summer course etc. rules (outside waiver block)
  if (extraCreditTotal > 0) {
    // Apply credit to target sections: add to section earned and to first row's earned
    for (var csi in sectionCredit) {
      if (sectionCredit.hasOwnProperty(csi)) {
        var secIdx = parseInt(csi);
        var cSec = sections[secIdx];
        cSec.earned_units = Math.min(cSec.earned_units + sectionCredit[csi], cSec.target_units || 999);
        cSec.progress = cSec.target_units > 0 ? cSec.earned_units / cSec.target_units : 0;
        cSec._hasCredit = true;
        // Also add credit to first row in the section (for row earned display)
        if (cSec.rows && cSec.rows.length > 0) {
          cSec.rows[0].rowEarned += sectionCredit[csi];
          if (!cSec.rows[0].consumed) cSec.rows[0].consumed = [];
          if (!cSec.rows[0].consumedCodes) cSec.rows[0].consumedCodes = [];
          // Add trigger codes to consumedCodes so they show green
          var triggers = sectionTriggers[csi] || [];
          for (var ti = 0; ti < triggers.length; ti++) {
            if (cSec.rows[0].consumedCodes.indexOf(triggers[ti]) < 0) {
              cSec.rows[0].consumedCodes.push(triggers[ti]);
            }
          }
        }
      }
    }
    // Recompute total from sections
    totalEarned = 0;
    for (var si = 0; si < sections.length; si++) totalEarned += sections[si].earned_units;
    totalEarned = Math.min(totalEarned, totalTarget);
    overall = totalTarget > 0 ? totalEarned / totalTarget : 0;
  }

  // Compute chip colors: green = consumed here, yellow = elsewhere, red = equiv, gray = waived
  for (var si = 0; si < sections.length; si++) {
    for (var ri = 0; ri < sections[si].rows.length; ri++) {
      var row = sections[si].rows[ri];
      row.chipFlags = {};
      for (var ci = 0; ci < row.codes.length; ci++) {
        var code = row.codes[ci].code;
        var wCanon = canonFn(code);
        var isWaived = studentCanonSet._waived && studentCanonSet._waived[wCanon];
        if ((row.matchedExact && row.matchedExact[code]) ||
            (row.matchedEquiv && row.matchedEquiv[code])) {
          var isWSatisfied = waiverSatisfiedSet[code];
          if (isWaived && !isWSatisfied) {
            row.chipFlags[code] = 'waived';
          } else if (row.consumedCodes && row.consumedCodes.indexOf(code) !== -1) {
            row.chipFlags[code] = 'consumed';
          } else if (row.matchedEquiv && row.matchedEquiv[code]) {
            row.chipFlags[code] = 'equiv';
          } else {
            row.chipFlags[code] = 'elsewhere';
          }
        }
      }
      // Waiver chips: codes that are waived but not matched
      if (waiverActive) {
        for (var ci = 0; ci < row.codes.length; ci++) {
          var wCode = row.codes[ci].code;
          if (waiverSet[wCode] && (!row.chipFlags || !row.chipFlags[wCode])) {
            row.chipFlags[wCode] = totalEarned >= totalTarget ? 'consumed' : 'waived';
          }
        }
      }
      // Count waived courses in this row for progress display
      // Only count UNSATISFIED waived codes that are also matched
      row.waivedCount = 0;
      if (waiverActive) {
        var mSet = {};
        if (row.matched) for (var mi = 0; mi < row.matched.length; mi++) mSet[row.matched[mi]] = true;
        for (var wci = 0; wci < row.codes.length; wci++) {
          var wcCode = row.codes[wci].code;
          if (waiverSet[wcCode] && mSet[canonFn(wcCode)] && !waiverSatisfiedSet[wcCode]) {
            row.waivedCount++;
          }
        }
      }
      // Split eqLost into external (used by other rows) vs truly wasted
      row.externalLost = 0; row.wastedLost = 0;
      var seenExt = {};
      for (var ci = 0; ci < (row.codes || []).length; ci++) {
        var canon = canonFn(row.codes[ci].code);
        if (seenExt[canon]) continue;
        if (!studentCanonSet[canon]) continue;
        seenExt[canon] = true;
        var totalRaw = studentRawUnits[canon] || studentUnits[canon] || 3;
        var consumedByThis = (row.consumedUnits && row.consumedUnits[canon]) || 0;
        var consumedTotal = usedCanonSet[canon] || 0;
        row.externalLost += Math.max(0, consumedTotal - consumedByThis);
        row.wastedLost += Math.max(0, totalRaw - consumedTotal);
      }
      if (row.wastedLost + row.externalLost > (row.eqLost || 0)) {
        row.wastedLost = Math.max(0, (row.eqLost || 0) - row.externalLost);
      }
    }
  }

  return {
    title: minorData.title,
    faculty: minorData.faculty,
    description: minorData.description || '',
    sections: sections,
    overall_progress: overall,
    total_target: totalTarget,
    total_earned: totalEarned,
    global_level_lost: globalLevelLost,
    global_level_note: glNote,
    global_fac_lost: globalFacLost,
    explanatory_notes: minorData.explanatory_notes || '',
    waiver_satisfied: waiverSatisfied,
    has_extra_credit: extraCreditTotal > 0
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
  html += '<span style="font-size:.75em;color:var(--muted);margin-left:4px;">(' + result.total_earned.toFixed(1) + '/' + result.total_target.toFixed(1) + 'u)</span>';
  html += '<span class="result-arrow" id="arrow-' + index + '">&#9660;</span>';
  html += '</div>';

  // Detail section
  html += '<div class="result-detail" id="detail-' + index + '">';
  if (result.description) {
    html += '<div class="detail-row" style="margin-bottom:10px;color:var(--muted);font-size:.88em;">' + result.description + '</div>';
  }
  if (result.global_level_lost && result.global_level_lost > 0) {
    html += '<div class="detail-row" style="margin-bottom:8px;color:#dc2626;font-size:.88em;">&#9888; ' + result.global_level_lost.toFixed(1) + ' units capped by global level constraint' + (result.global_level_note || '') + '</div>';
  }
  if (result.global_fac_lost && result.global_fac_lost > 0) {
    html += '<div class="detail-row" style="margin-bottom:8px;color:#dc2626;font-size:.88em;">&#9888; ' + result.global_fac_lost.toFixed(1) + ' units exceeded same-faculty cap</div>';
  }
  for (var si = 0; si < result.sections.length; si++) {
    var sec = result.sections[si];
    var secPct = Math.round(sec.progress * 100);
    html += '<div class="detail-section">';
    html += '<h4>' + sec.label + ' (' + secPct + '% &middot; ' + sec.earned_units.toFixed(1) + '/' + (sec.target_units_max != null ? sec.target_units.toFixed(1) + '-' + sec.target_units_max.toFixed(1) : sec.target_units.toFixed(1)) + ' units)</h4>';

    for (var ri = 0; ri < sec.rows.length; ri++) {
      var row = sec.rows[ri];
      html += '<div class="detail-row">';
      html += '<div class="detail-row-text">' + row.text + ' <strong>(';
      if (row.strategy === 'pick_n') {
        var showCount = (row.effCount != null) ? row.effCount : row.matched.length;
        html += showCount + '/' + row.n + ' courses';
        // Only show unit target if the original JSON had an explicit unit requirement
        if (row.units_needed) {
          html += ' (' + row.rowTarget.toFixed(1) + ' units)';
        }
      } else if (row.strategy === 'units') {
        var uTarget = row.units_needed || 0;
        html += row.rowEarned.toFixed(1) + '/' + (row.units_needed_max != null ? uTarget.toFixed(1) + '-' + row.units_needed_max.toFixed(1) : uTarget.toFixed(1)) + ' units';
      } else if (row.strategy === 'all') {
        var dcount = row.dedup_count || row.codes.length;
        var wc = row.waivedCount || 0;
        html += Math.max(0, (row.matched ? row.matched.length : 0) - wc) + '/' + dcount + ' courses';
      } else if (row.strategy === 'or_group') {
        var bestGroup = 0;
        var bestProg = 0;
        if (row.or_groups) {
          for (var gi = 0; gi < row.or_groups.length; gi++) {
            var gd = row.or_groups[gi].dedup_count || row.or_groups[gi].codes.length;
            var gm = 0;
            for (var ci = 0; ci < row.or_groups[gi].codes.length; ci++) {
              var orCode = row.or_groups[gi].codes[ci];
              var flagOr = row.chipFlags && row.chipFlags[orCode];
              if (flagOr === 'consumed' || flagOr === 'elsewhere' ||
                  (row.matchedEquiv && row.matchedEquiv[orCode])) gm++;
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
          var flag = row.chipFlags && row.chipFlags[codeObj.code];
          if (flag === 'consumed') {
            cls2 += ' matched';
          } else if (flag === 'waived') {
            cls2 += ' waived';
          } else if (flag === 'elsewhere') {
            cls2 += ' elsewhere';
          } else if (row.matchedEquiv && row.matchedEquiv[codeObj.code]) {
            cls2 += ' equiv';
          }
          html += '<span class="' + cls2 + '">' + codeObj.code + '</span>';
        }
        html += '</div>';
      }

      if (row.level_constraint) {
        var constraints = row.level_constraint;
        if (!Array.isArray(constraints)) constraints = [constraints];
        for (var lci = 0; lci < constraints.length; lci++) {
          var lc = constraints[lci];
          var lv = 'Level ' + lc.min_level;
          if (lc.max_level) lv += '-' + lc.max_level;
          if (lc.min_units_needed) lv += ': need ' + lc.min_units_needed + ' units';
          if (lc.min_courses_needed) lv += ': need ' + lc.min_courses_needed + ' courses';
          html += '<div class="detail-row-stat">&#9888; Level constraint: ' + lv + '</div>';
        }
      }
      if (row.externalLost && row.externalLost > 0 && !result.has_extra_credit) {
        html += '<div class="detail-row-stat" style="color:#dc2626;">&#9888; ' + row.externalLost.toFixed(1) + ' units not used for this section</div>';
      }
      if (row.isNotesEquiv) {
        html += '<div class="detail-row-stat" style="color:var(--warn);">&#9432; Explanatory Notes equivalent course used</div>';
      } else if (row.waivedCount > 0) {
        if (result.waiver_satisfied) {
          html += '<div class="detail-row-stat" style="color:var(--warn);">&#9432; Waiver satisfied — replacement courses cover exemption</div>';
        } else {
          html += '<div class="detail-row-stat" style="color:var(--warn);">&#9432; Course waived — replacement needed</div>';
        }
      } else {
        if (row.wastedLost && row.wastedLost > 0) {
          html += '<div class="detail-row-stat" style="color:#dc2626;">&#9888; ' + row.wastedLost.toFixed(1) + ' units from equivalent courses not counted</div>';
        }
        if (!row.externalLost && !row.wastedLost && row.hasTrueEquivMatch) {
          html += '<div class="detail-row-stat" style="color:var(--warn);">&#9432; Equivalent course matches used</div>';
        }
      }
      if (row.levelLost && row.levelLost > 0) {
        html += '<div class="detail-row-stat" style="color:#dc2626;">&#9888; ' + row.levelLost.toFixed(1) + ' units capped by level constraint</div>';
      }
      if (row.sectionLost && row.sectionLost > 0 && !(row.levelLost && row.levelLost > 0) && !result.has_extra_credit) {
        html += '<div class="detail-row-stat" style="color:#dc2626;">&#9888; ' + row.sectionLost.toFixed(1) + ' units unusable (requirement already satisfied)</div>';
      }
      // Subject bucket warnings
      if (row.subjectMin && row.actualSubj < row.subjectMin) {
        html += '<div class="detail-row-stat" style="color:var(--warn);">&#9432; Need at least ' + row.subjectMin + ' subject areas (have ' + row.actualSubj + ')</div>';
      }
      if (row.subjectLost && row.subjectLost > 0) {
        html += '<div class="detail-row-stat" style="color:#dc2626;">&#9888; ' + row.subjectLost.toFixed(1) + ' units exceeding subject bucket limits</div>';
      }
      if (row.bucketInfo && !row.bucketOk) {
        for (var bi = 0; bi < row.bucketInfo.length; bi++) {
          var b = row.bucketInfo[bi];
          var buckLbl = b.label || ((b.isNeg ? 'non-' : '') + b.prefix);
          if (b.min_units && b.units < b.min_units) {
            html += '<div class="detail-row-stat" style="color:var(--warn);">&#9432; Need ' + b.min_units + ' units from ' + buckLbl + ' (have ' + b.units.toFixed(1) + ')</div>';
          }
          if (b.min_courses && b.courses < b.min_courses) {
            html += '<div class="detail-row-stat" style="color:var(--warn);">&#9432; Need ' + b.min_courses + ' course(s) from ' + buckLbl + ' (have ' + b.courses + ')</div>';
          }
          if (b.max_units && b.units > b.max_units) {
            html += '<div class="detail-row-stat" style="color:var(--warn);">&#9432; At most ' + b.max_units + ' units from ' + buckLbl + ' (have ' + b.units.toFixed(1) + ')</div>';
          }
        }
      }

      html += '</div>';
    }
    html += '</div>';
  }
  if (result.explanatory_notes) {
    html += '<div class="detail-notes"><h4>Explanatory Notes</h4>' + result.explanatory_notes + '</div>';
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
    var card = document.getElementById('card-' + index);
    if (card) card.scrollIntoView({behavior:'smooth', block:'start'});
  }
}

function renderResults(results) {
  var container = document.getElementById('results');
  if (!container) return;

  // Sort by progress descending, then alphabetically by title
  results.sort(function(a, b) {
    var diff = b.overall_progress - a.overall_progress;
    if (diff !== 0) return diff;
    return (a.title || '').localeCompare(b.title || '');
  });

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

  // Update summary (parsed courses section stays collapsed by default)
  var summaryEl = document.getElementById('parse-summary');
  if (summaryEl) summaryEl.innerHTML = PARSED_COURSES.length + ' courses, ' + totalUnits.toFixed(1) + ' units';

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

  // Scroll to parse section so it's at the top
  setTimeout(function() {
    var parse = document.getElementById('parse-section');
    if (parse) parse.scrollIntoView({behavior:'smooth', block:'start'});
  }, 50);
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
    <h2 style="margin-top:0;">1. Paste CUSIS Academic Records</h2>
    <p class="summary">Go to CUSIS &rarr; Academic Records, copy all text (Ctrl+A, Ctrl+C) and paste below.</p>
    <textarea id="input-text" placeholder="Paste your CUSIS academic records here..."></textarea>
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
