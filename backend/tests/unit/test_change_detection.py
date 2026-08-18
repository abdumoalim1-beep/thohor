from app.measurement.change_detection import compare_page_states


def test_no_before_state_means_page_created():
    result = compare_page_states(None, {"title": "t"})
    assert result.page_created is True
    assert result.has_meaningful_change() is True


def test_detects_title_and_h1_change():
    before = {"title": "old title", "h1": "old h1", "content_hash": "abc", "internal_links": [], "json_ld": []}
    after = {"title": "new title", "h1": "new h1", "content_hash": "abc", "internal_links": [], "json_ld": []}
    result = compare_page_states(before, after)
    assert result.title_changed is True
    assert result.h1_changed is True
    assert result.text_changed is False
    assert result.has_meaningful_change() is True


def test_detects_content_hash_change_as_text_changed():
    before = {"title": "t", "h1": "h", "content_hash": "abc", "internal_links": [], "json_ld": []}
    after = {"title": "t", "h1": "h", "content_hash": "xyz", "internal_links": [], "json_ld": []}
    result = compare_page_states(before, after)
    assert result.text_changed is True
    assert result.title_changed is False


def test_detects_new_internal_links():
    before = {"title": "t", "h1": "h", "content_hash": "abc", "internal_links": ["https://x/a"], "json_ld": []}
    after = {
        "title": "t", "h1": "h", "content_hash": "abc",
        "internal_links": ["https://x/a", "https://x/b"], "json_ld": [],
    }
    result = compare_page_states(before, after)
    assert result.links_added == ["https://x/b"]
    assert result.has_meaningful_change() is True


def test_detects_schema_added():
    before = {"title": "t", "h1": "h", "content_hash": "abc", "internal_links": [], "json_ld": []}
    after = {"title": "t", "h1": "h", "content_hash": "abc", "internal_links": [], "json_ld": [{"@type": "FAQPage"}]}
    result = compare_page_states(before, after)
    assert result.schema_added is True


def test_no_change_detected_when_identical():
    state = {"title": "t", "h1": "h", "content_hash": "abc", "internal_links": ["https://x/a"], "json_ld": []}
    result = compare_page_states(state, dict(state))
    assert result.has_meaningful_change() is False
