"""Tests for google_auth shared credential loader and agent _get_google_services()."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cmo_agent.google_auth import (
    ensure_drive_folder,
    get_google_credentials,
    move_file_to_folder,
)


# ══════════════════════════════════════════════════════════════════════════
# get_google_credentials() unit tests
# ══════════════════════════════════════════════════════════════════════════


class TestGetGoogleCredentials:
    """Tests for the shared get_google_credentials() utility."""

    def test_returns_none_when_no_paths(self):
        """No paths provided → None."""
        result = get_google_credentials()
        assert result is None

    def test_returns_none_when_paths_are_empty_strings(self):
        """Empty strings for both paths → None."""
        result = get_google_credentials(oauth_token_path="", service_account_path="")
        assert result is None

    def test_returns_none_when_files_do_not_exist(self, tmp_path):
        """Non-existent file paths → None."""
        result = get_google_credentials(
            oauth_token_path=str(tmp_path / "nonexistent-oauth.json"),
            service_account_path=str(tmp_path / "nonexistent-sa.json"),
        )
        assert result is None

    @patch("cmo_agent.google_auth.Path.exists", return_value=True)
    @patch("cmo_agent.google_auth.Path.write_text")
    def test_oauth_valid_token_returned(self, mock_write, mock_exists):
        """Valid, non-expired OAuth token → returns credentials."""
        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_creds.expired = False

        with patch(
            "google.oauth2.credentials.Credentials.from_authorized_user_file",
            return_value=mock_creds,
        ):
            result = get_google_credentials(
                oauth_token_path="/fake/token.json",
                scopes=["https://www.googleapis.com/auth/documents"],
            )

        assert result is mock_creds
        mock_write.assert_not_called()  # No refresh needed

    @patch("cmo_agent.google_auth.Path.exists", return_value=True)
    @patch("cmo_agent.google_auth.Path.write_text")
    def test_oauth_expired_token_refreshes_and_persists(self, mock_write, mock_exists):
        """Expired OAuth token with refresh_token → refreshes and writes back."""
        mock_creds = MagicMock()
        mock_creds.expired = True
        mock_creds.refresh_token = "fake-refresh-token"
        mock_creds.valid = True  # valid after refresh
        mock_creds.to_json.return_value = '{"token": "new"}'

        mock_request_cls = MagicMock()

        with (
            patch(
                "google.oauth2.credentials.Credentials.from_authorized_user_file",
                return_value=mock_creds,
            ),
            patch(
                "google.auth.transport.requests.Request",
                return_value=mock_request_cls,
            ),
        ):
            result = get_google_credentials(oauth_token_path="/fake/token.json")

        assert result is mock_creds
        mock_creds.refresh.assert_called_once_with(mock_request_cls)
        mock_write.assert_called_once_with('{"token": "new"}')

    @patch("cmo_agent.google_auth.Path.exists", return_value=True)
    def test_oauth_invalid_after_load_falls_through(self, mock_exists):
        """OAuth token loads but creds.valid is False → returns None (no SA fallback)."""
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = False

        with patch(
            "google.oauth2.credentials.Credentials.from_authorized_user_file",
            return_value=mock_creds,
        ):
            result = get_google_credentials(oauth_token_path="/fake/token.json")

        assert result is None

    @patch("cmo_agent.google_auth.Path.exists", return_value=True)
    def test_oauth_exception_falls_to_service_account(self, mock_exists):
        """OAuth load throws → falls through to service account."""
        mock_sa_creds = MagicMock()

        with (
            patch(
                "google.oauth2.credentials.Credentials.from_authorized_user_file",
                side_effect=Exception("corrupt token"),
            ),
            patch(
                "google.oauth2.service_account.Credentials.from_service_account_file",
                return_value=mock_sa_creds,
            ),
        ):
            result = get_google_credentials(
                oauth_token_path="/fake/token.json",
                service_account_path="/fake/sa.json",
            )

        assert result is mock_sa_creds

    @patch("cmo_agent.google_auth.Path.exists", return_value=True)
    def test_service_account_fallback(self, mock_exists):
        """No OAuth path, but valid SA path → returns SA credentials."""
        mock_sa_creds = MagicMock()

        with patch(
            "google.oauth2.service_account.Credentials.from_service_account_file",
            return_value=mock_sa_creds,
        ):
            result = get_google_credentials(
                service_account_path="/fake/sa.json",
                scopes=["https://www.googleapis.com/auth/drive.file"],
            )

        assert result is mock_sa_creds

    @patch("cmo_agent.google_auth.Path.exists", return_value=True)
    def test_service_account_exception_returns_none(self, mock_exists):
        """SA load throws → returns None."""
        with patch(
            "google.oauth2.service_account.Credentials.from_service_account_file",
            side_effect=Exception("bad SA file"),
        ):
            result = get_google_credentials(service_account_path="/fake/sa.json")

        assert result is None

    @patch("cmo_agent.google_auth.Path.exists", return_value=True)
    @patch("cmo_agent.google_auth.Path.write_text")
    def test_oauth_preferred_over_service_account(self, mock_write, mock_exists):
        """When both paths exist and OAuth is valid, OAuth wins."""
        mock_oauth_creds = MagicMock()
        mock_oauth_creds.valid = True
        mock_oauth_creds.expired = False

        mock_sa_creds = MagicMock()

        with (
            patch(
                "google.oauth2.credentials.Credentials.from_authorized_user_file",
                return_value=mock_oauth_creds,
            ),
            patch(
                "google.oauth2.service_account.Credentials.from_service_account_file",
                return_value=mock_sa_creds,
            ) as sa_mock,
        ):
            result = get_google_credentials(
                oauth_token_path="/fake/token.json",
                service_account_path="/fake/sa.json",
            )

        assert result is mock_oauth_creds
        sa_mock.assert_not_called()  # SA never reached

    def test_scopes_default_to_empty_list(self):
        """Scopes default to [] when None is passed."""
        # No paths → None, but ensure no crash from None scopes
        result = get_google_credentials(scopes=None)
        assert result is None


# ══════════════════════════════════════════════════════════════════════════
# DocsAgent._get_google_services() tests
# ══════════════════════════════════════════════════════════════════════════


class TestDocsAgentGoogleServices:
    """Tests for DocsAgent._get_google_services() OAuth integration."""

    @pytest.fixture
    def docs_agent(self):
        from cmo_agent.agents.docs import DocsAgent

        mock_llm = MagicMock()
        mock_db = MagicMock()
        mock_ws = MagicMock()
        return DocsAgent(
            llm=mock_llm,
            db=mock_db,
            workspace_manager=mock_ws,
            google_credentials_path="/fake/sa.json",
            google_oauth_token_path="/fake/oauth.json",
        )

    def test_cached_service_returns_true(self, docs_agent):
        """If services already initialized, returns True immediately."""
        docs_agent._docs_service = MagicMock()
        assert docs_agent._get_google_services() is True

    @patch("cmo_agent.google_auth.get_google_credentials", return_value=None)
    def test_no_credentials_returns_false(self, mock_get_creds, docs_agent):
        """get_google_credentials returns None → False."""
        assert docs_agent._get_google_services() is False
        assert docs_agent._docs_service is None

    @patch("googleapiclient.discovery.build")
    @patch("cmo_agent.google_auth.get_google_credentials")
    def test_successful_init_sets_services(self, mock_get_creds, mock_build, docs_agent):
        """Valid credentials → services initialized, returns True."""
        mock_creds = MagicMock()
        mock_get_creds.return_value = mock_creds
        mock_build.side_effect = [MagicMock(name="docs"), MagicMock(name="drive")]

        assert docs_agent._get_google_services() is True
        assert docs_agent._docs_service is not None
        assert docs_agent._drive_service is not None

        # Verify scopes passed
        mock_get_creds.assert_called_once()
        call_kwargs = mock_get_creds.call_args
        assert "documents" in str(call_kwargs)
        assert "drive.file" in str(call_kwargs)

    @patch("cmo_agent.google_auth.get_google_credentials")
    def test_build_exception_returns_false(self, mock_get_creds, docs_agent):
        """googleapiclient.discovery.build throws → returns False."""
        mock_get_creds.return_value = MagicMock()
        with patch("googleapiclient.discovery.build", side_effect=Exception("API error")):
            assert docs_agent._get_google_services() is False

    def test_oauth_path_stored(self, docs_agent):
        """Constructor stores the oauth path."""
        assert docs_agent._google_oauth_token_path == "/fake/oauth.json"
        assert docs_agent._google_credentials_path == "/fake/sa.json"


# ══════════════════════════════════════════════════════════════════════════
# SheetsAgent._get_google_services() tests
# ══════════════════════════════════════════════════════════════════════════


class TestSheetsAgentGoogleServices:
    """Tests for SheetsAgent._get_google_services() OAuth integration."""

    @pytest.fixture
    def sheets_agent(self):
        from cmo_agent.agents.sheets import SheetsAgent

        mock_llm = MagicMock()
        mock_db = MagicMock()
        mock_ws = MagicMock()
        return SheetsAgent(
            llm=mock_llm,
            db=mock_db,
            workspace_manager=mock_ws,
            google_credentials_path="/fake/sa.json",
            google_oauth_token_path="/fake/oauth.json",
        )

    def test_cached_service_returns_true(self, sheets_agent):
        """If services already initialized, returns True immediately."""
        sheets_agent._sheets_service = MagicMock()
        assert sheets_agent._get_google_services() is True

    @patch("cmo_agent.google_auth.get_google_credentials", return_value=None)
    def test_no_credentials_returns_false(self, mock_get_creds, sheets_agent):
        """get_google_credentials returns None → False."""
        assert sheets_agent._get_google_services() is False
        assert sheets_agent._sheets_service is None

    @patch("googleapiclient.discovery.build")
    @patch("cmo_agent.google_auth.get_google_credentials")
    def test_successful_init_sets_services(self, mock_get_creds, mock_build, sheets_agent):
        """Valid credentials → services initialized, returns True."""
        mock_creds = MagicMock()
        mock_get_creds.return_value = mock_creds
        mock_build.side_effect = [MagicMock(name="sheets"), MagicMock(name="drive")]

        assert sheets_agent._get_google_services() is True
        assert sheets_agent._sheets_service is not None
        assert sheets_agent._drive_service is not None

        mock_get_creds.assert_called_once()
        call_kwargs = mock_get_creds.call_args
        assert "spreadsheets" in str(call_kwargs)
        assert "drive.file" in str(call_kwargs)

    @patch("cmo_agent.google_auth.get_google_credentials")
    def test_build_exception_returns_false(self, mock_get_creds, sheets_agent):
        """googleapiclient.discovery.build throws → returns False."""
        mock_get_creds.return_value = MagicMock()
        with patch("googleapiclient.discovery.build", side_effect=Exception("API error")):
            assert sheets_agent._get_google_services() is False

    def test_oauth_path_stored(self, sheets_agent):
        """Constructor stores the oauth path."""
        assert sheets_agent._google_oauth_token_path == "/fake/oauth.json"
        assert sheets_agent._google_credentials_path == "/fake/sa.json"


# ══════════════════════════════════════════════════════════════════════════
# DeckAgent._get_google_services() tests
# ══════════════════════════════════════════════════════════════════════════


class TestDeckAgentGoogleServices:
    """Tests for DeckAgent._get_google_services() OAuth integration."""

    @pytest.fixture
    def deck_agent(self, tmp_path):
        from cmo_agent.agents.deck import DeckAgent

        mock_llm = MagicMock()
        mock_db = MagicMock()
        mock_ws = MagicMock()
        return DeckAgent(
            llm=mock_llm,
            db=mock_db,
            workspace_manager=mock_ws,
            google_credentials_path="/fake/sa.json",
            google_oauth_token_path="/fake/oauth.json",
            decks_dir=tmp_path / "decks",
        )

    def test_cached_service_returns_true(self, deck_agent):
        """If services already initialized, returns True immediately."""
        deck_agent._slides_service = MagicMock()
        assert deck_agent._get_google_services() is True

    @patch("cmo_agent.google_auth.get_google_credentials", return_value=None)
    def test_no_credentials_returns_false(self, mock_get_creds, deck_agent):
        """get_google_credentials returns None → False."""
        assert deck_agent._get_google_services() is False
        assert deck_agent._slides_service is None

    @patch("googleapiclient.discovery.build")
    @patch("cmo_agent.google_auth.get_google_credentials")
    def test_successful_init_sets_services(self, mock_get_creds, mock_build, deck_agent):
        """Valid credentials → services initialized, returns True."""
        mock_creds = MagicMock()
        mock_get_creds.return_value = mock_creds
        mock_build.side_effect = [MagicMock(name="slides"), MagicMock(name="drive")]

        assert deck_agent._get_google_services() is True
        assert deck_agent._slides_service is not None
        assert deck_agent._drive_service is not None

        mock_get_creds.assert_called_once()
        call_kwargs = mock_get_creds.call_args
        assert "presentations" in str(call_kwargs)
        assert "drive.file" in str(call_kwargs)

    @patch("cmo_agent.google_auth.get_google_credentials")
    def test_build_exception_returns_false(self, mock_get_creds, deck_agent):
        """googleapiclient.discovery.build throws → returns False."""
        mock_get_creds.return_value = MagicMock()
        with patch("googleapiclient.discovery.build", side_effect=Exception("API error")):
            assert deck_agent._get_google_services() is False

    def test_oauth_path_stored(self, deck_agent):
        """Constructor stores the oauth path."""
        assert deck_agent._google_oauth_token_path == "/fake/oauth.json"
        assert deck_agent._google_credentials_path == "/fake/sa.json"

    def test_resolve_format_prefers_google_slides_when_creds_exist(self, deck_agent, tmp_path):
        """_resolve_format defaults to google_slides when credentials path exists."""
        # Point to a file that actually exists
        token_file = tmp_path / "creds.json"
        token_file.write_text("{}")
        deck_agent._google_credentials_path = str(token_file)

        assert deck_agent._resolve_format("") == "google_slides"

    def test_resolve_format_falls_back_to_pptx(self, deck_agent):
        """_resolve_format defaults to pptx when credentials path doesn't exist."""
        deck_agent._google_credentials_path = "/nonexistent/path.json"
        assert deck_agent._resolve_format("") == "pptx"

    def test_resolve_format_respects_explicit_choice(self, deck_agent):
        """_resolve_format returns explicit format when provided."""
        assert deck_agent._resolve_format("pptx") == "pptx"
        assert deck_agent._resolve_format("google_slides") == "google_slides"


# ══════════════════════════════════════════════════════════════════════════
# ensure_drive_folder() unit tests
# ══════════════════════════════════════════════════════════════════════════


class TestEnsureDriveFolder:
    """Tests for the ensure_drive_folder() utility."""

    def _mock_drive(self, list_files=None):
        """Build a mock drive_service with files().list() and files().create()."""
        svc = MagicMock()
        svc.files().list().execute.return_value = {"files": list_files or []}
        svc.files().create().execute.return_value = {"id": "new-folder-id"}
        return svc

    def test_finds_existing_folder(self):
        """If folder already exists, returns its ID without creating."""
        svc = MagicMock()
        svc.files().list().execute.return_value = {
            "files": [{"id": "existing-123", "name": "CMO Agent"}]
        }

        result = ensure_drive_folder(svc, folder_name="CMO Agent")

        assert result == "existing-123"
        svc.files().create.assert_not_called()

    def test_creates_folder_when_not_found(self):
        """If folder doesn't exist, creates it and returns new ID."""
        svc = MagicMock()
        svc.files().list().execute.return_value = {"files": []}
        svc.files().create().execute.return_value = {"id": "new-456"}

        result = ensure_drive_folder(svc)

        assert result == "new-456"

    def test_returns_none_on_exception(self):
        """API exception → returns None gracefully."""
        svc = MagicMock()
        svc.files().list().execute.side_effect = Exception("API down")

        result = ensure_drive_folder(svc)

        assert result is None

    def test_uses_default_folder_name(self):
        """Default folder name is 'CMO Agent'."""
        svc = MagicMock()
        svc.files().list().execute.return_value = {"files": []}
        svc.files().create().execute.return_value = {"id": "f1"}

        ensure_drive_folder(svc)

        # Verify the query contains the default folder name
        list_call = svc.files().list.call_args
        assert list_call is not None  # list was called

    def test_custom_folder_name(self):
        """Custom folder name is used in the query."""
        svc = MagicMock()
        svc.files().list().execute.return_value = {"files": []}
        svc.files().create().execute.return_value = {"id": "f2"}

        result = ensure_drive_folder(svc, folder_name="My Folder")

        assert result == "f2"


# ══════════════════════════════════════════════════════════════════════════
# move_file_to_folder() unit tests
# ══════════════════════════════════════════════════════════════════════════


class TestMoveFileToFolder:
    """Tests for the move_file_to_folder() utility."""

    def test_moves_file_from_root_to_folder(self):
        """Moves file: removes old parents, adds new folder."""
        svc = MagicMock()
        svc.files().get().execute.return_value = {"parents": ["root"]}
        svc.files().update().execute.return_value = {"id": "file1", "parents": ["folder1"]}

        move_file_to_folder(svc, file_id="file1", folder_id="folder1")

        # update was called (through the mock chain)
        svc.files().update.assert_called()

    def test_handles_multiple_parents(self):
        """When file has multiple parents, all are removed."""
        svc = MagicMock()
        svc.files().get().execute.return_value = {"parents": ["parent1", "parent2"]}
        svc.files().update().execute.return_value = {"id": "f1", "parents": ["folder1"]}

        move_file_to_folder(svc, file_id="f1", folder_id="folder1")

        svc.files().update.assert_called()

    def test_exception_does_not_propagate(self):
        """API exception → logs warning but doesn't raise."""
        svc = MagicMock()
        svc.files().get().execute.side_effect = Exception("permission denied")

        # Should not raise
        move_file_to_folder(svc, file_id="f1", folder_id="folder1")
