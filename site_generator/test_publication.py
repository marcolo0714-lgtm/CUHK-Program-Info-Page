"""Regression checks for crawlable pages, lazy details and meaningful dates."""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

from site_generator import publication, site_metadata


def test_local_navigation_uses_real_files_without_changing_hosted_urls():
    harness = r"""
const vm = require('vm'), assert = require('assert');
function link(base, target) {
    const context = {location:new URL(base), URL, window:{}, document:{baseURI:base,addEventListener(){}}};
    vm.createContext(context);
    vm.runInContext(SCRIPT, context);
    return context.window.publicationLink(target);
}
assert.equal(link('file:///C:/repo/site/2026_27/index.html', 'minors/Physics'), 'file:///C:/repo/site/2026_27/minors/Physics.html');
assert.equal(link('http://localhost:8765/site/major/2026_27/index.html', 'majors/B.Sc._in_Physics?a=b#courses'), 'http://localhost:8765/site/major/2026_27/majors/B.Sc._in_Physics.html?a=b#courses');
assert.equal(link('http://127.0.0.1:8765/2026_27/minors/Physics.html', '../'), 'http://127.0.0.1:8765/2026_27/index.html');
assert.equal(link('http://localhost:8765/2026_27/index.html', 'checker'), 'http://localhost:8765/2026_27/checker.html');
assert.equal(link('https://cuhk-minor.coffeebreak.work/2026_27/', 'minors/Physics'), 'minors/Physics');
assert.equal(link('file:///C:/repo/site/2026_27/index.html', 'https://example.com/'), 'https://example.com/');
assert.equal(link('file:///C:/repo/site/2026_27/index.html', '#courses'), '#courses');
"""
    subprocess.run(["node", "-e", "const SCRIPT=" + json.dumps(publication.LOCAL_SCRIPT) + ";" + harness], check=True)


def test_deferred_details_load_from_scripts_and_allow_retry():
    harness = r"""
const assert = require('assert');
let attempts=0, cells=[], messages=[], retry, restored='', applied=0;
const cell={dataset:{courseDetail:'row'},set outerHTML(value){restored=value;cells=[];}};
cells=[cell];
const container={open:true,dataset:{},querySelectorAll:()=>cells,querySelector:()=>messages[0],
 addEventListener(){},append:message=>messages.push(message)};
global.window={applyTableSettings:()=>applied++};
global.document={getElementById:()=>({dataset:{src:'../assets/details.js',fallback:'fallback.html'}}),
 querySelectorAll:selector=>selector==='details.course-details'?[container]:[],
 createElement:tag=>({remove(){messages=[];},addEventListener:(event,fn)=>{retry=fn;},append(){}}),
 head:{append(script){attempts++;queueMicrotask(()=>{if(attempts===1)script.onerror();
 else{script.courseDetails={row:'<td>Monday</td>'};script.onload();}});}}};
"""
    checks = r"""
setTimeout(async()=>{
 try{
  assert.equal(cell.textContent,'Unavailable');assert.equal(messages.length,1);
  retry();await new Promise(resolve=>setTimeout(resolve,0));
  assert.equal(restored,'<td>Monday</td>');assert.equal(applied,1);assert.equal(attempts,2);
 }catch(error){console.error(error);process.exitCode=1;}
},0);
"""
    subprocess.run(["node", "-e", harness + publication.DETAIL_SCRIPT + checks], check=True)


def test_canonical_links_preserve_dotted_programmes_and_query_strings():
    assert publication.canonical_link("../majors/B.Sc._in_Physics.html?scheme=senior#a") == "../majors/B.Sc._in_Physics?scheme=senior#a"
    assert publication.canonical_link("../index.html") == "../"
    assert publication.canonical_link("https://example.com/about.html") == "https://example.com/about.html"


def test_lazy_details_keep_crawlable_courses_and_complete_fallback(tmp_path):
    source = """<html><head><style>td { padding:9px; }</style></head><body>
    <h1>Physics requirements</h1><details class="course-details">
    <summary>Show courses</summary><table style="--course-code-width:10%">
    <tr><td class="col-code">PHYS 1001</td><td class="col-title">Mechanics</td>
    <td class="col-t1-schedule">Monday 10:30</td><td class="col-t2-schedule">—</td>
    <td class="col-prereq">Prerequisite: PHYS 1000</td><td class="col-minors"><a href="../../../2026_27/minors/Physics">Physics</a></td></tr></table></details>
    <a href="../minors/Physics.html">Physics minor</a>
    <script>window.ready = true;</script></body></html>"""
    path = tmp_path / "major/2026_27/majors/Physics.html"
    with patch.object(publication, "SITE", tmp_path):
        result = publication.prepare_page(source, path)
    assert "PHYS 1001" in result and "Mechanics" in result
    assert "Prerequisite: PHYS 1000" not in result
    soup = BeautifulSoup(result, "html.parser")
    source_node = soup.find(id="course-detail-source")
    script = (path.parent / source_node["data-src"]).resolve().read_text(encoding="utf-8")
    payload = json.loads(script.removeprefix("document.currentScript.courseDetails=").removesuffix(";"))
    assert len(payload) == 1
    assert "Prerequisite: PHYS 1000" in next(iter(payload.values()))
    assert "Monday 10:30" in next(iter(payload.values()))
    fallback = (path.parent / source_node["data-fallback"]).resolve().read_text(encoding="utf-8")
    assert "Prerequisite: PHYS 1000" in fallback and "Monday 10:30" in fallback
    assert 'content="noindex,follow"' in fallback
    assert 'href="../../2026_27/minors/Physics"' in fallback
    assert soup.find("a", string="Physics minor")["href"] == "../minors/Physics"
    assert soup.find("script", src=True) is not None
    for element in soup.select('script[src], link[rel="stylesheet"]'):
        reference = element.get("src", element.get("href"))
        assert not reference.startswith("/"), reference
        assert (path.parent / reference).resolve().is_file(), reference


def test_freshness_ignores_shared_asset_changes_but_tracks_requirements(tmp_path):
    page = tmp_path / "index.html"
    state = tmp_path / "freshness.json"
    page.write_text('<html><head><link href="/assets/shared/first.css"></head><body><h1>Take 6 units</h1></body></html>', encoding="utf-8")
    with patch.object(site_metadata, "FRESHNESS_FILE", state):
        site_metadata.page_freshness([page], tmp_path)
        previous = json.loads(state.read_text(encoding="utf-8"))
        previous["index.html"]["updated"] = "2020-01-01"
        state.write_text(json.dumps(previous), encoding="utf-8")
        page.write_text(page.read_text(encoding="utf-8").replace("first.css", "second.css"), encoding="utf-8")
        assert site_metadata.page_freshness([page], tmp_path)["/index"] == "2020-01-01"
        page.write_text(page.read_text(encoding="utf-8").replace("6 units", "9 units"), encoding="utf-8")
        assert site_metadata.page_freshness([page], tmp_path)["/index"] != "2020-01-01"


def test_asset_cleanup_preserves_json_and_nested_fallback_dependencies(tmp_path):
    with patch.object(publication, "SITE", tmp_path):
        details = publication.asset('{"row":"<td>Monday</td>"}', ".json", "course-details")
        css = publication.asset("td { color: black; }", ".css")
        fallback = publication.asset(f'<link href="{css}">', ".html", "course-details")
        obsolete = publication.asset("obsolete", ".js")
    (tmp_path / "index.html").write_text(
        f'<div data-src="{details}" data-fallback="{fallback}"></div>', encoding="utf-8"
    )
    publication.prune_assets(tmp_path)
    assert (tmp_path / details.lstrip("/")).exists()
    assert (tmp_path / fallback.lstrip("/")).exists()
    assert (tmp_path / css.lstrip("/")).exists()
    assert not (tmp_path / obsolete.lstrip("/")).exists()


def test_freshness_tracks_checker_data_version(tmp_path):
    page = tmp_path / "checker.html"
    state = tmp_path / "freshness.json"
    page.write_text('<head><meta name="checker-data-version" content="before"></head>', encoding="utf-8")
    with patch.object(site_metadata, "FRESHNESS_FILE", state):
        site_metadata.page_freshness([page], tmp_path)
        saved = json.loads(state.read_text(encoding="utf-8"))
        saved["checker.html"]["updated"] = "2020-01-01"
        state.write_text(json.dumps(saved), encoding="utf-8")
        page.write_text(page.read_text(encoding="utf-8").replace("before", "after"), encoding="utf-8")
        assert site_metadata.page_freshness([page], tmp_path)["/checker"] != "2020-01-01"


def test_generated_scheme_pages_have_unique_canonicals_and_complete_requirements():
    root = Path(__file__).resolve().parents[1]
    for year in ("2024_25", "2025_26", "2026_27"):
        for source in (root / "major_extraction/major_json" / year).glob("*.json"):
            data = json.loads(source.read_text(encoding="utf-8"))
            schemes = data.get("requirement_schemes", [])
            if not schemes:
                continue
            default = next(
                (scheme for scheme in schemes if scheme.get("kind") == "standard"),
                next((scheme for scheme in schemes if scheme.get("default")), schemes[0]),
            )
            for scheme in schemes:
                stem = source.stem if scheme is default else source.stem + "--" + scheme["id"]
                path = root / "site/major" / year / "majors" / (stem + ".html")
                soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
                assert path.stat().st_size <= 1_500_000, path
                assert soup.find("link", rel="canonical")["href"] == (
                    f"https://cuhk-minor.coffeebreak.work/major/{year}/majors/{stem}"
                )
                panels = soup.select("section.requirement-scheme")
                assert len(panels) == 1 and not panels[0].has_attr("hidden"), path
                assert panels[0]["data-requirement-scheme"] == scheme["id"], path
                expected_sections = sum(len(part.get("sections", [])) for part in scheme["parts"])
                assert len(panels[0].find_all("h2")) >= expected_sections, path
                selector = soup.find(id="requirementSchemeSelect")
                if selector:
                    assert selector.find("option", selected=True)["value"] == scheme["id"], path
                    assert len(selector.find_all("option")) == len(schemes), path
                    assert not soup.select('nav[aria-label="Requirement schemes"]'), path
