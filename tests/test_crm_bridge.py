from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
PAGES = ("wonju", "sales", "valueup", "system")


def test_pages_load_closed_crm_bridge_and_announce_exact_page():
    for page in PAGES:
        html = (DOCS / f"{page}.html").read_text(encoding="utf-8")
        assert '<script src="./crm-bridge.js"></script>' in html
        assert f'BringValueScope.ready("{page}")' in html


def test_selectable_pages_emit_public_record_only():
    expected = {
        "wonju": 'BringValueScope.select("wonju"',
        "sales": 'BringValueScope.select("sales"',
        "valueup": 'BringValueScope.select("valueup"',
    }
    for page, call in expected.items():
        html = (DOCS / f"{page}.html").read_text(encoding="utf-8")
        assert call in html

    system = (DOCS / "system.html").read_text(encoding="utf-8")
    assert "BringValueScope.select(" not in system


def test_bridge_has_closed_public_message_contract_and_no_secret_fields():
    source = (DOCS / "crm-bridge.js").read_text(encoding="utf-8")
    assert "BRING_VALUESCOPE_READY" in source
    assert "BRING_VALUESCOPE_SELECTION" in source
    assert "Object.keys(record)" in source
    for field in ("sourcePage", "externalId", "name", "address", "lat", "lng", "category", "summary"):
        assert f'"{field}"' in source
    for forbidden in ("firebaseToken", "idToken", "refreshToken", "password", "authorization"):
        assert forbidden not in source


def test_bridge_bounds_strings_coordinates_and_parent_delivery():
    source = (DOCS / "crm-bridge.js").read_text(encoding="utf-8")
    assert "MAX_STRING_BYTES" in source
    assert "TextEncoder" in source
    assert "lat < 37" in source
    assert "lat > 38" in source
    assert "lng < 127" in source
    assert "lng > 129" in source
    assert 'window.parent.postMessage(envelope, "*")' in source
    assert "window.parent === window" not in source
