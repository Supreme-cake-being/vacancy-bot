import pytest
from app.scraper.diff_engine import DiffEngine, VacancyItem

SAMPLE_HTML = """
<html><body>
  <ul class="jobs">
    <li class="job-item">
      <h3><a href="/jobs/1">Python Developer</a></h3>
    </li>
    <li class="job-item">
      <h3><a href="/jobs/2">DevOps Engineer</a></h3>
    </li>
  </ul>
</body></html>
"""

UPDATED_HTML = """
<html><body>
  <ul class="jobs">
    <li class="job-item">
      <h3><a href="/jobs/1">Python Developer</a></h3>
    </li>
    <li class="job-item">
      <h3><a href="/jobs/2">DevOps Engineer</a></h3>
    </li>
    <li class="job-item">
      <h3><a href="/jobs/3">Data Engineer</a></h3>
    </li>
  </ul>
</body></html>
"""

EMPTY_HTML = "<html><body><p>No positions available.</p></body></html>"

def test_no_changes():
    engine = DiffEngine(css_selector=".job-item")
    vacancies, _ = engine.extract(SAMPLE_HTML)
    known_hashes = {v.hash for v in vacancies}

    result = engine.compare(SAMPLE_HTML, known_hashes)
    assert result.new_vacancies == []
    assert not result.has_new

def test_detects_new_vacancy():
    engine = DiffEngine(css_selector=".job-item")
    initial, _ = engine.extract(SAMPLE_HTML)
    known_hashes = {v.hash for v in initial}

    result = engine.compare(UPDATED_HTML, known_hashes)
    assert len(result.new_vacancies) == 1
    assert "Data Engineer" in result.new_vacancies[0].title

def test_all_new_on_first_run():
    engine = DiffEngine(css_selector=".job-item")
    # Empty known_hashes simulates first run
    result = engine.compare(SAMPLE_HTML, known_hashes=set())
    assert len(result.new_vacancies) == 2

def test_keyword_match():
    v = VacancyItem(title="Senior Python Developer", url="/jobs/1")
    assert v.matches_keywords(["Python"])
    assert v.matches_keywords(["python"])      # case insensitive
    assert v.matches_keywords(["Senior", "Go"]) # any match
    assert not v.matches_keywords(["Java"])

def test_no_keywords_matches_all():
    v = VacancyItem(title="Any Position", url="/jobs/1")
    assert v.matches_keywords([])  # empty list = no filter

def test_absolute_url_relative():
    v = VacancyItem(title="Dev", url="/jobs/123")
    assert v.absolute_url("https://company.com") == "https://company.com/jobs/123"

def test_absolute_url_already_absolute():
    v = VacancyItem(title="Dev", url="https://other.com/jobs/123")
    assert v.absolute_url("https://company.com") == "https://other.com/jobs/123"

def test_empty_page_returns_no_vacancies():
    engine = DiffEngine(css_selector=".job-item")
    result = engine.compare(EMPTY_HTML, known_hashes=set())
    assert result.new_vacancies == []

def test_page_hash_detects_change():
    engine = DiffEngine(css_selector=".job-item")
    hash1 = engine.compute_page_hash(SAMPLE_HTML)
    hash2 = engine.compute_page_hash(UPDATED_HTML)
    assert hash1 != hash2

def test_page_hash_ignores_scripts():
    html1 = "<html><body><div class='job-item'><h3>Dev</h3></div></body></html>"
    html2 = (
        "<html><body>"
        "<script>var x = Math.random()</script>"
        "<div class='job-item'><h3>Dev</h3></div>"
        "</body></html>"
    )
    engine = DiffEngine()
    assert engine.compute_page_hash(html1) == engine.compute_page_hash(html2)