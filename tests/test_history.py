"""Tests for history service and page versioning endpoints."""

import time
from services.history import save_version, list_versions, get_version


def test_history_service(tmp_path, monkeypatch):
    from core import config
    monkeypatch.setattr(config, "WIKIS_ROOT", tmp_path / "wikis")
    
    wiki = "main"
    slug = "test-page"
    
    v1 = save_version(wiki, slug, "# Version 1\nContent 1")
    assert v1.exists()
    
    time.sleep(1.05)
    
    v2 = save_version(wiki, slug, "# Version 2\nContent 2")
    assert v2.exists()
    
    versions = list_versions(wiki, slug)
    assert len(versions) == 2
    
    content = get_version(wiki, slug, versions[0]["id"])
    assert content == "# Version 2\nContent 2"


def test_history_api_endpoints(client, auth_cookie):
    client.cookies.update(auth_cookie)
    res = client.get("/LLMWikiNG/wiki/main/nonexistent/history")
    assert res.status_code == 200
    data = res.json()
    assert data["slug"] == "nonexistent"
    assert data["versions"] == []
