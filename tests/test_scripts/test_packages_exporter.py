import os
import tempfile
import pytest

from alws.config import settings
from alws.models import SignKey
from scripts.packages_exporter import Exporter
from tests.mock_classes import BaseAsyncTestCase

IN_GITHUB_ACTIONS = os.getenv("GITHUB_ACTIONS") is not None


class TestPackagesExporter(BaseAsyncTestCase):
    @pytest.mark.skipif(
        not settings.test_sign_key_id, reason="Testing sign key is not provided"
    )
    async def test_repomd_signer(self, sign_key: SignKey, tmp_path):
        exporter = Exporter(
            pulp_client=None, repodata_cache_dir='~/.cache/pulp_exporter'
        )
        key_id = sign_key.keyid
        token = await exporter.get_sign_server_token()
        temp_file = tmp_path / "tempfile.txt"
        temp_file.write_bytes(b'Hello world!')
        res = await exporter.sign_repomd_xml(str(temp_file), key_id, token)
        assert res['error'] is None
