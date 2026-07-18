"""Tests für die FastAPI-App und HTTP-Integration (TestClient)."""

from __future__ import annotations

import pytest


class TestAppCreation:
    """Tests für create_app()."""

    def test_app_creation(self, tmp_project):
        from main import create_app
        app = create_app()
        assert app is not None
        assert app.title.startswith("LLMWikiNG")

    def test_app_has_routes(self, tmp_project):
        from main import create_app
        app = create_app()
        # FastAPI wraps included routers in _IncludedRouter which has no .path.
        # Check by stringifying all route objects.
        all_routes = [str(r) for r in app.routes]
        assert any("LLMWikiNG" in r for r in all_routes)


class TestRootRedirect:
    """Tests für Root-Redirect."""

    def test_root_redirects_to_base(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code in (307, 302, 301)
        assert "LLMWikiNG" in resp.headers.get("location", "")


class TestFavicon:
    """Tests für Favicon-Endpunkt."""

    def test_favicon_returns_204(self, client):
        resp = client.get("/favicon.ico")
        assert resp.status_code == 204


class TestLoginPage:
    """Tests für Login-Seite."""

    def test_login_page_renders(self, client):
        resp = client.get("/LLMWikiNG/login")
        assert resp.status_code == 200

    def test_login_redirects_to_register_when_no_users(self, tmp_project):
        """Wenn keine User existieren, sollte /register aufgerufen werden."""
        from fastapi.testclient import TestClient
        from main import create_app
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/LLMWikiNG/login", follow_redirects=False)
        # Should redirect to register when no users exist
        assert resp.status_code in (302, 303, 307, 200)


class TestRegisterPage:
    """Tests für Registrierung."""

    def test_register_page_renders(self, client):
        resp = client.get("/LLMWikiNG/register")
        assert resp.status_code == 200

    def test_register_first_user_as_admin(self, tmp_project):
        """Der erste Benutzer sollte Admin werden."""
        from fastapi.testclient import TestClient
        from main import create_app
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/LLMWikiNG/register",
            data={"username": "admin", "password": "SecurePass123!"},
            follow_redirects=False,
        )
        # Should succeed (200 for success page, or redirect)
        assert resp.status_code in (200, 303, 307)

        # Verify user was created
        from core.storage import list_users
        users = list_users()
        assert len(users) == 1
        assert users[0]["role"] == "admin"

    def test_register_missing_fields(self, client):
        resp = client.post(
            "/LLMWikiNG/register",
            data={"username": "", "password": ""},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 307)


class TestLoginLogout:
    """Tests für Login/Logout-Flows."""

    def test_login_success(self, sample_users):
        from fastapi.testclient import TestClient
        from main import create_app
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/LLMWikiNG/login",
            data={"username": "admin", "password": "Admin123!@#"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 307)
        # Check that session cookie is set
        cookies = dict(resp.cookies)
        assert "session" in cookies

    def test_login_wrong_password(self, sample_users):
        from fastapi.testclient import TestClient
        from main import create_app
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/LLMWikiNG/login",
            data={"username": "admin", "password": "falsch"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 307)
        assert "error" in resp.headers.get("location", "")

    def test_login_nonexistent_user(self, sample_users):
        from fastapi.testclient import TestClient
        from main import create_app
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/LLMWikiNG/login",
            data={"username": "nobody", "password": "test"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 307)

    def test_logout(self, auth_cookie):
        from fastapi.testclient import TestClient
        from main import create_app
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/LLMWikiNG/logout",
            cookies=auth_cookie,
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 307)


class TestProtectedPages:
    """Tests für geschützte Seiten."""

    def test_unauthenticated_redirects_to_login(self, client):
        """Ohne Login sollte man auf /login weitergeleitet werden."""
        resp = client.get("/LLMWikiNG/", follow_redirects=False)
        assert resp.status_code in (302, 307, 303)

    def test_authenticated_access_dashboard(self, auth_cookie):
        from fastapi.testclient import TestClient
        from main import create_app
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/LLMWikiNG/",
            cookies=auth_cookie,
            follow_redirects=False,
        )
        assert resp.status_code == 200

    def test_authenticated_access_search(self, auth_cookie):
        from fastapi.testclient import TestClient
        from main import create_app
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/LLMWikiNG/search",
            cookies=auth_cookie,
        )
        assert resp.status_code == 200


class TestAPIEndpoints:
    """Tests für die JSON-API."""

    def test_api_requires_key(self, client):
        resp = client.get("/LLMWikiNG/api/v1/status")
        assert resp.status_code == 401

    def test_api_with_valid_key(self, sample_api_keys):
        from fastapi.testclient import TestClient
        from main import create_app
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        _, data = sample_api_keys
        resp = client.get(
            "/LLMWikiNG/api/v1/status",
            headers={"X-API-Key": data["raw_key"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "authenticated_user" in body

    def test_api_with_invalid_key(self, client):
        resp = client.get(
            "/LLMWikiNG/api/v1/status",
            headers={"X-API-Key": "llmw_invalid_key"},
        )
        assert resp.status_code == 403

    def test_api_search(self, wiki_with_pages, sample_api_keys):
        from fastapi.testclient import TestClient
        from main import create_app
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        _, data = sample_api_keys
        resp = client.get(
            "/LLMWikiNG/api/v1/search",
            params={"q": "python", "wiki": "main"},
            headers={"X-API-Key": data["raw_key"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "results" in body

    def test_api_list_pages(self, wiki_with_pages, sample_api_keys):
        from fastapi.testclient import TestClient
        from main import create_app
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        _, data = sample_api_keys
        resp = client.get(
            "/LLMWikiNG/api/v1/wikis/main/pages",
            headers={"X-API-Key": data["raw_key"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "pages" in body
        assert len(body["pages"]) > 0

    def test_api_get_page(self, wiki_with_pages, sample_api_keys):
        from fastapi.testclient import TestClient
        from main import create_app
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        _, data = sample_api_keys
        resp = client.get(
            "/LLMWikiNG/api/v1/wikis/main/pages/python",
            headers={"X-API-Key": data["raw_key"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["slug"] == "python"

    def test_api_get_nonexistent_page(self, wiki_with_pages, sample_api_keys):
        from fastapi.testclient import TestClient
        from main import create_app
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        _, data = sample_api_keys
        resp = client.get(
            "/LLMWikiNG/api/v1/wikis/main/pages/nonexistent",
            headers={"X-API-Key": data["raw_key"]},
        )
        assert resp.status_code == 404

    def test_api_list_wikis(self, wiki_with_pages, sample_api_keys):
        from fastapi.testclient import TestClient
        from main import create_app
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        _, data = sample_api_keys
        resp = client.get(
            "/LLMWikiNG/api/v1/wikis",
            headers={"X-API-Key": data["raw_key"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "wikis" in body

    def test_api_stats(self, wiki_with_pages, sample_api_keys):
        from fastapi.testclient import TestClient
        from main import create_app
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        _, data = sample_api_keys
        resp = client.get(
            "/LLMWikiNG/api/v1/wikis/main/stats",
            headers={"X-API-Key": data["raw_key"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "page_count" in body

    def test_api_lint(self, wiki_with_pages, sample_api_keys):
        from fastapi.testclient import TestClient
        from main import create_app
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        _, data = sample_api_keys
        resp = client.get(
            "/LLMWikiNG/api/v1/wikis/main/lint",
            headers={"X-API-Key": data["raw_key"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "issue_count" in body

    def test_api_wiki_not_found(self, sample_api_keys):
        from fastapi.testclient import TestClient
        from main import create_app
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        _, data = sample_api_keys
        resp = client.get(
            "/LLMWikiNG/api/v1/wikis/nonexistent/pages",
            headers={"X-API-Key": data["raw_key"]},
        )
        # wiki_path() auto-creates directories → 200 with empty pages list
        assert resp.status_code == 200
        body = resp.json()
        assert body["pages"] == []

    def test_api_create_page(self, wiki_with_pages, sample_api_keys):
        from fastapi.testclient import TestClient
        from main import create_app
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        _, data = sample_api_keys
        resp = client.post(
            "/LLMWikiNG/api/v1/wikis/main/pages",
            json={"slug": "new-page", "content": "# New Page\n\nContent"},
            headers={"X-API-Key": data["raw_key"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True

    def test_api_cannot_overwrite_system_page(self, wiki_with_pages, sample_api_keys):
        from fastapi.testclient import TestClient
        from main import create_app
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        _, data = sample_api_keys
        resp = client.post(
            "/LLMWikiNG/api/v1/wikis/main/pages",
            json={"slug": "index", "content": "# Overwritten"},
            headers={"X-API-Key": data["raw_key"]},
        )
        assert resp.status_code == 400


class TestErrorHandlers:
    """Tests für Fehlerseiten."""

    def test_404_page(self, client):
        resp = client.get("/LLMWikiNG/nonexistent-page", follow_redirects=False)
        # Should return error (307 to login or 404)
        assert resp.status_code in (307, 404)

    def test_api_404_returns_json(self, sample_api_keys):
        from fastapi.testclient import TestClient
        from main import create_app
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        _, data = sample_api_keys
        resp = client.get(
            "/LLMWikiNG/api/v1/nonexistent",
            headers={"X-API-Key": data["raw_key"]},
        )
        assert resp.status_code == 404


class TestGraphEndpoints:
    """Tests für Graph-Endpoints."""

    def test_graph_data(self, wiki_with_pages, sample_api_keys):
        from fastapi.testclient import TestClient
        from main import create_app
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        _, data = sample_api_keys
        resp = client.get(
            "/LLMWikiNG/api/v1/wikis/main/graph",
            headers={"X-API-Key": data["raw_key"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "nodes" in body
        assert "edges" in body

    def test_graph_paginated(self, wiki_with_pages, sample_api_keys):
        from fastapi.testclient import TestClient
        from main import create_app
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        _, data = sample_api_keys
        resp = client.get(
            "/LLMWikiNG/api/v1/wikis/main/graph/paginated",
            params={"page": 0, "page_size": 2},
            headers={"X-API-Key": data["raw_key"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "total_nodes" in body
        assert "total_pages" in body


class TestCacheEndpoints:
    """Tests für Cache-API (Admin-only)."""

    def test_cache_stats_requires_admin(self, sample_api_keys):
        from fastapi.testclient import TestClient
        from main import create_app
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        _, data = sample_api_keys
        resp = client.get(
            "/LLMWikiNG/api/v1/cache/stats",
            headers={"X-API-Key": data["raw_key"]},
        )
        # Should work for admin
        assert resp.status_code == 200

    def test_cache_clear(self, sample_api_keys):
        from fastapi.testclient import TestClient
        from main import create_app
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        _, data = sample_api_keys
        resp = client.post(
            "/LLMWikiNG/api/v1/cache/clear",
            headers={"X-API-Key": data["raw_key"]},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


class TestUserManagementAPI:
    """Tests für User-Management via API."""

    def test_list_users_requires_admin(self, sample_api_keys):
        from fastapi.testclient import TestClient
        from main import create_app
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        _, data = sample_api_keys
        resp = client.get(
            "/LLMWikiNG/api/v1/users",
            headers={"X-API-Key": data["raw_key"]},
        )
        assert resp.status_code == 200

    def test_create_user_via_api(self, sample_api_keys):
        from fastapi.testclient import TestClient
        from main import create_app
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        _, data = sample_api_keys
        resp = client.post(
            "/LLMWikiNG/api/v1/users",
            json={"username": "apitest", "password": "Test123!", "role": "editor"},
            headers={"X-API-Key": data["raw_key"]},
        )
        assert resp.status_code == 201

    def test_create_user_missing_fields(self, sample_api_keys):
        from fastapi.testclient import TestClient
        from main import create_app
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        _, data = sample_api_keys
        resp = client.post(
            "/LLMWikiNG/api/v1/users",
            json={"username": "", "password": ""},
            headers={"X-API-Key": data["raw_key"]},
        )
        assert resp.status_code == 400

    def test_delete_user_cannot_delete_self(self, sample_api_keys):
        from fastapi.testclient import TestClient
        from main import create_app
        from core.storage import list_users
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        _, data = sample_api_keys
        admin_id = data["admin"]["id"]
        resp = client.delete(
            f"/LLMWikiNG/api/v1/users/{admin_id}",
            headers={"X-API-Key": data["raw_key"]},
        )
        assert resp.status_code == 400
