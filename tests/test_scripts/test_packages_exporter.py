import os
import tempfile

import pytest
from syncer import sync

from scripts.packages_exporter import Exporter

IN_GITHUB_ACTIONS = os.getenv("GITHUB_ACTIONS") is not None


@pytest.mark.skip(
    reason="See https://github.com/AlmaLinux/build-system/issues/204"
)
def test_repomd_signer():
    exporter = Exporter(
        pulp_client=None, repodata_cache_dir='~/.cache/pulp_exporter'
    )
    db_keys = sync(exporter.get_sign_keys())
    key_id = db_keys[0]['keyid']
    with tempfile.NamedTemporaryFile() as fp:
        fp.write(b'Hello world!')
        res = sync(exporter.sign_repomd_xml(fp.name, key_id))
        assert res['error'] is None
