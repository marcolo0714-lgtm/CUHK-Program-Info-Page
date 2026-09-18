"""Build the course-to-minor lookup used by minor and major course tables.

The checker output is the authoritative source because it already contains the
resolved course overrides and all equivalence rules detected from explanatory
notes.  Keeping this lookup downstream of the checker prevents the information
pages from developing a second, subtly different interpretation of a minor.
"""

from __future__ import annotations

import html
import json
import re
from collections import defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def _plain_text(value: object) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _normalized(value: object) -> str:
    text = html.unescape(str(value or "")).casefold().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalized_clause(value: object) -> str:
    text = html.unescape(str(value or "")).casefold().replace("&", " and ")
    text = re.sub(r"[^a-z0-9,;.]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _exclusion_text(notes: object) -> str:
    """Return only explanatory-note sentences that declare inapplicability."""
    plain = _plain_text(notes)
    starts = list(re.finditer(r"this minor programme is (?:also )?not applicable", plain, re.I))
    clauses = []
    for match in starts:
        tail = plain[match.start():]
        end = re.search(r"(?=\s+(?:\d+\.|\[[a-z#* ]+\])\s+)", tail[match.end() - match.start():], re.I)
        if end:
            tail = tail[: match.end() - match.start() + end.start()]
        clauses.append(tail.strip())
    return " ".join(clauses)


DEGREE_EXPANSIONS = {
    "b a": "bachelor of arts",
    "b b a": "bachelor of business administration",
    "b ed": "bachelor of education",
    "b eng": "bachelor of engineering",
    "b s sc": "bachelor of social science",
    "b sc": "bachelor of science",
    "ll b": "bachelor of laws",
}


def _major_aliases(title: object) -> set[str]:
    """Return conservative aliases suitable for matching an exclusion clause."""
    normalized = _normalized(title)
    aliases = {normalized}
    for abbreviation, expansion in DEGREE_EXPANSIONS.items():
        if normalized.startswith(abbreviation + " "):
            aliases.add(expansion + normalized[len(abbreviation):])
    for marker in (" in ", " - "):
        if marker in normalized:
            aliases.add(normalized.split(marker, 1)[1])
    aliases.update(
        alias.removesuffix(" programme").strip()
        for alias in list(aliases)
        if alias.endswith(" programme")
    )
    # Very short aliases (for example "law") produce unsafe substring matches.
    return {alias for alias in aliases if len(alias) >= 6}


def minor_matches_major_name(minor: dict[str, object], major: dict[str, object] | None) -> bool:
    """Whether the minor and major have the same programme subject name."""
    if not major:
        return False
    minor_name = _normalized(minor.get("title"))
    return bool(minor_name and minor_name in _major_aliases(major.get("title")))


def minor_applies_to_major(minor: dict[str, object], major: dict[str, object] | None) -> bool:
    """Whether a minor may be shown on a particular major programme page."""
    if not major:
        return True
    exclusion = _normalized_clause(minor.get("exclusion_text"))
    if not exclusion:
        return True

    faculty = _normalized(major.get("faculty"))
    faculties = {_normalized(value) for value in major.get("faculties", []) or []}
    faculties.add(faculty)
    if (
        "programmes under the faculty of business administration" in exclusion
        and "business administration" in faculties
    ):
        return False

    # An alias must end as a listed programme/major item.  This prevents a
    # standalone "Quantitative Finance" major from matching the longer listed
    # programme "Quantitative Finance and Risk Management Science".
    normalized_title = _normalized(major.get("title"))
    full_aliases = {normalized_title}
    for abbreviation, expansion in DEGREE_EXPANSIONS.items():
        if normalized_title.startswith(abbreviation + " "):
            full_aliases.add(expansion + normalized_title[len(abbreviation):])
    qualified = re.compile(
        r"\b(?:double degree|dual degree|double major|second major|2nd major|"
        r"multidisciplinary stream|stream of|degree option)\b"
    )
    for alias in sorted(_major_aliases(major.get("title")), key=len, reverse=True):
        pattern = rf"(?:^|\s){re.escape(alias)}(?=\s*(?:major|programme|programmes|,|;|\.|$))"
        for match in re.finditer(pattern, exclusion):
            # A qualifier before a core-name occurrence means that occurrence
            # names only a stream, second major, or combined programme.  Do not
            # let it suppress the whole standalone major page.  Qualifiers
            # appearing *after* an earlier direct item must not invalidate that
            # earlier match (for example, "Chinese Language and Literature"
            # followed by its double-major variant).
            left = max(exclusion.rfind(mark, 0, match.start()) for mark in ";.") + 1
            prefix = exclusion[left:match.start()]
            if alias not in full_aliases and qualified.search(prefix):
                continue
            rights = [position for mark in ",;." if (position := exclusion.find(mark, match.end())) >= 0]
            right = min(rights) if rights else len(exclusion)
            suffix = exclusion[match.end():right]
            following_qualifier = qualified.search(suffix)
            if following_qualifier and not qualified.search(alias):
                before_qualifier = suffix[:following_qualifier.start()]
                # A repeated name denotes a direct programme followed by a
                # qualified variant of that programme; retain the direct match.
                if not re.search(rf"\b{re.escape(alias)}\b", before_qualifier):
                    continue
            return False
    return True


def load_minor_course_index(year: str, root: Path = REPO_ROOT) -> dict[str, list[dict[str, object]]]:
    """Return ``course code -> eligible minor records`` for one admission year."""
    path = root / "site_tempdata" / f"checker_minors_{year}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    memberships: dict[str, list[dict[str, object]]] = defaultdict(list)

    for stem, minor in payload.get("minors", {}).items():
        direct_codes = {
            item.get("code")
            for section in minor.get("sections", [])
            for row in section.get("rows", [])
            for item in row.get("codes", [])
            if item.get("code")
        }
        eq_norm = minor.get("eq_norm", {}) or {}
        direct_canon = {eq_norm.get(code, code) for code in direct_codes}
        eligible_codes = set(direct_codes)
        eligible_codes.update(
            code for code, canonical in eq_norm.items() if canonical in direct_canon
        )
        eligible_codes.update(
            canonical for canonical in eq_norm.values() if canonical in direct_canon
        )
        for group in minor.get("and_eq_groups", []) or []:
            canonical = group.get("canon")
            if eq_norm.get(canonical, canonical) in direct_canon:
                eligible_codes.update(group.get("courses", []) or [])
        # Credit-waiver triggers immediately earn minor units.  Ordinary
        # waiver triggers do not count until a substitute is taken, so those
        # triggers are intentionally excluded.
        eligible_codes.update(
            rule.get("trigger")
            for rule in minor.get("waiver_rules", []) or []
            if rule.get("credit_units") and rule.get("trigger")
        )

        record = {
            "stem": stem,
            "title": minor.get("title") or stem.replace("_", " "),
            "exclusion_text": _exclusion_text(minor.get("explanatory_notes")),
        }
        for code in eligible_codes:
            memberships[code].append(record)

    for records in memberships.values():
        records.sort(key=lambda item: str(item["title"]).casefold())
    return dict(memberships)
