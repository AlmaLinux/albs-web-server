import os
import tempfile

import pytest
from syncer import sync

from scripts.packages_exporter import Exporter

IN_GITHUB_ACTIONS = os.getenv("GITHUB_ACTIONS") is not None


@pytest.mark.skip(
    reason="""
        This test needs to be rewritten.

        First, it needs to be converted into an async test.

        We need to bring up a configured sign_file instance when setting up the
        test environment. This is, prepare everything to run:

        `docker compose run --no-deps web_server db sign_file ...`

        The sign_file service should:
        * Have a user inside db
        * A key in gpg database

        Also, there is no point in getting the sign_keys from web_server as we
        haven't loaded any keys into testing db. We should load sign keys into
        db to request keys from web_server if we want this test to work that
        way. Which can be easily done using a fixture.
        In any case, I propose to, simply, pass the key_id of the key(s) that
        we add into sign_file service when setting up the test environment and
        skip the call to `exporter.get_sign_keys`, which can be tested
        elsewhere, but not in this file.

        Bear in mind that the exporter should know the sign_file user
        credentials as they are used to request a token from sign_file
        service.

        pytest's tmp_path fixture can be of help to deal with tmp_files,
        i.e.:
        ```
            def test_repomd_signer(tmp_path: Path):
                tmp_file = tmp_path / "file.txt"
                tmp_file.write_bytes(b"Hello world!")
                ...
        ```
    """
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
