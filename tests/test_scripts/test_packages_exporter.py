import logging

import pytest

from scripts.exporters.base_exporter import BasePulpExporter
from scripts.exporters.packages_exporter import PackagesExporter
from tests.mock_classes import BaseAsyncTestCase

FAKE_SIGNATURE = "-----BEGIN PGP SIGNATURE-----\nfake\n-----END PGP SIGNATURE-----"


def _make_exporter() -> PackagesExporter:
    # Bypass __init__: it needs the createrepo_c binary, a Pulp client and
    # writable cache dirs, none of which are relevant to the sign flow (and
    # createrepo_c isn't installed in the test image). We only exercise the
    # sign-server calls, which need nothing but a logger.
    exporter = PackagesExporter.__new__(PackagesExporter)
    exporter.logger = logging.getLogger("test-packages-exporter")
    return exporter


class TestPackagesExporter(BaseAsyncTestCase):
    async def test_repomd_signer(self, monkeypatch, tmp_path):
        # Stub the only network chokepoint. The sign server exposes 'token'
        # (returns an auth token) and 'sign' (returns the detached ASC).
        async def fake_make_request(self, method, endpoint, **kwargs):
            if endpoint == "token":
                return {"token": "test-token"}
            if endpoint == "sign":
                return FAKE_SIGNATURE
            raise AssertionError(f"unexpected endpoint {endpoint!r}")

        monkeypatch.setattr(BasePulpExporter, "make_request", fake_make_request)

        exporter = _make_exporter()
        token = await exporter.get_sign_server_token()
        assert token == "test-token"

        temp_file = tmp_path / "repomd.xml"
        temp_file.write_bytes(b"Hello world!")
        res = await exporter.sign_repomd_xml(temp_file, "1234567890ABCDEF", token)
        assert res["error"] is None
        assert res["asc_content"] == FAKE_SIGNATURE

    async def test_repomd_signer_reports_error(self, monkeypatch, tmp_path):
        # An empty sign-server response is treated as a failure. max_attempts=1
        # so no retry backoff sleep is hit.
        async def fake_make_request(self, method, endpoint, **kwargs):
            return ""

        monkeypatch.setattr(BasePulpExporter, "make_request", fake_make_request)

        exporter = _make_exporter()
        temp_file = tmp_path / "repomd.xml"
        temp_file.write_bytes(b"Hello world!")
        res = await exporter.sign_repomd_xml(
            temp_file, "1234567890ABCDEF", "test-token", max_attempts=1
        )
        assert res["asc_content"] is None
        assert res["error"] == "sign server returned empty response"
