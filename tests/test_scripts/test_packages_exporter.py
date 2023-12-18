import tempfile

from scripts.packages_exporter import Exporter
from syncer import sync


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
