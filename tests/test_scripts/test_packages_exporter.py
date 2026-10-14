import hashlib
import logging
from pathlib import Path
from types import SimpleNamespace

import createrepo_c as cr
import pytest

from scripts.exporters import packages_exporter
from scripts.exporters.base_exporter import BasePulpExporter
from scripts.exporters.packages_exporter import PackagesExporter, SignatureCache
from tests.mock_classes import BaseAsyncTestCase

FAKE_SIGNATURE = "-----BEGIN PGP SIGNATURE-----\nfake\n-----END PGP SIGNATURE-----"

PLATFORM_KEY = "d36cb86cb86b3716"
FOREIGN_KEY = "199e2f91fd431d51"
PACKAGE = "foo-1.1-1.el10.noarch.rpm"
# Same size, different bytes: a package re-signed under the same file name
SIGNED_BY_PLATFORM_KEY = b"A" * 64
SIGNED_BY_FOREIGN_KEY = b"B" * 64
SIGNER = {
    SIGNED_BY_PLATFORM_KEY: PLATFORM_KEY,
    SIGNED_BY_FOREIGN_KEY: FOREIGN_KEY,
}


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


def _primary_package(file_name: str, content: bytes, size: int, epoch="0"):
    name, version, release_arch = file_name.rsplit("-", 2)
    release, arch, _ = release_arch.rsplit(".", 2)
    pkg = cr.Package()
    pkg.name = name
    pkg.epoch = epoch
    pkg.version = version
    pkg.release = release
    pkg.arch = arch
    pkg.checksum_type = "sha256"
    pkg.pkgId = hashlib.sha256(content).hexdigest()
    pkg.location_href = f"Packages/{file_name[0]}/{file_name}"
    pkg.size_package = size
    return pkg


def _write_repodata(repodata_dir: Path, packages: list):
    repodata_dir.mkdir(parents=True, exist_ok=True)
    primary_path = repodata_dir / "primary.xml.gz"
    # createrepo_c refuses to overwrite, unlike a repodata re-download
    primary_path.unlink(missing_ok=True)
    primary = cr.PrimaryXmlFile(str(primary_path))
    primary.set_num_of_pkgs(len(packages))
    for pkg in packages:
        primary.add_pkg(pkg)
    primary.close()
    record = cr.RepomdRecord("primary", str(primary_path))
    record.fill(cr.SHA256)
    repomd = cr.Repomd()
    repomd.set_record(record)
    (repodata_dir / "repomd.xml").write_text(repomd.xml_dump())


def _write_repo(repo_dir: Path, packages: dict, primary_sizes: dict = None):
    """
    Lay out an exported repository: the packages in Packages/ and the
    repodata Pulp would publish for them next to it.
    """
    packages_dir = repo_dir / "Packages"
    packages_dir.mkdir(parents=True, exist_ok=True)
    primary_packages = []
    for file_name, content in packages.items():
        (packages_dir / file_name).write_bytes(content)
        size = (primary_sizes or {}).get(file_name, len(content))
        primary_packages.append(_primary_package(file_name, content, size))
    _write_repodata(repo_dir / "repodata", primary_packages)
    return str(packages_dir)


@pytest.fixture
def read_packages(monkeypatch):
    """
    Replace reading RPM headers with a lookup by file content and record
    which packages were actually read.
    """
    read = []

    def fake_read_package_signer(ts, pkg_path):
        read.append(Path(pkg_path).name)
        return SIGNER[Path(pkg_path).read_bytes()]

    monkeypatch.setattr(
        packages_exporter, "read_package_signer", fake_read_package_signer
    )
    return read


def _make_signature_checker(tmp_path, repo_path, repodata_matches=True):
    exporter = _make_exporter()
    exporter.known_subkeys = {}
    exporter.export_error_file = str(tmp_path / "export.err")
    exporter.repodata_matches_export = {repo_path: repodata_matches}
    return exporter


def _check(exporter, repo_path, cache, key_id=PLATFORM_KEY):
    sign_keys = [SimpleNamespace(keyid=key_id.upper())]
    exporter.check_rpms_signature(repo_path, sign_keys, cache)


def _export_errors(exporter) -> str:
    path = Path(exporter.export_error_file)
    return path.read_text() if path.exists() else ""


def test_signature_cache_skips_unchanged_packages(tmp_path, read_packages):
    repo_path = _write_repo(
        tmp_path / "repo", {PACKAGE: SIGNED_BY_PLATFORM_KEY}
    )
    exporter = _make_signature_checker(tmp_path, repo_path)
    cache_path = tmp_path / "signatures.json"
    logger = exporter.logger

    cache = SignatureCache(cache_path, logger)
    _check(exporter, repo_path, cache)
    cache.save(prune=True)
    assert read_packages == [PACKAGE]

    cache = SignatureCache(cache_path, logger)
    _check(exporter, repo_path, cache)
    assert read_packages == [PACKAGE]
    assert _export_errors(exporter) == ""


def test_signature_cache_rechecks_package_replaced_under_same_name(
    tmp_path, read_packages
):
    repo_path = _write_repo(
        tmp_path / "repo", {PACKAGE: SIGNED_BY_PLATFORM_KEY}
    )
    exporter = _make_signature_checker(tmp_path, repo_path)
    cache_path = tmp_path / "signatures.json"
    cache = SignatureCache(cache_path, exporter.logger)
    _check(exporter, repo_path, cache)
    cache.save(prune=True)

    # Same file name and size, but another checksum in the repodata
    _write_repo(tmp_path / "repo", {PACKAGE: SIGNED_BY_FOREIGN_KEY})
    cache = SignatureCache(cache_path, exporter.logger)
    _check(exporter, repo_path, cache)

    assert read_packages == [PACKAGE, PACKAGE]
    assert f"{PACKAGE} {FOREIGN_KEY}" in _export_errors(exporter)


def test_signature_cache_unused_when_repodata_is_another_version(
    tmp_path, read_packages
):
    repo_path = _write_repo(
        tmp_path / "repo", {PACKAGE: SIGNED_BY_PLATFORM_KEY}
    )
    exporter = _make_signature_checker(
        tmp_path, repo_path, repodata_matches=False
    )
    cache = SignatureCache(tmp_path / "signatures.json", exporter.logger)
    _check(exporter, repo_path, cache)
    _check(exporter, repo_path, cache)

    assert read_packages == [PACKAGE, PACKAGE]


def test_signature_cache_unused_when_size_differs_from_repodata(
    tmp_path, read_packages
):
    repo_path = _write_repo(
        tmp_path / "repo",
        {PACKAGE: SIGNED_BY_PLATFORM_KEY},
        primary_sizes={PACKAGE: len(SIGNED_BY_PLATFORM_KEY) + 1},
    )
    exporter = _make_signature_checker(tmp_path, repo_path)
    cache = SignatureCache(tmp_path / "signatures.json", exporter.logger)
    _check(exporter, repo_path, cache)
    _check(exporter, repo_path, cache)

    assert read_packages == [PACKAGE, PACKAGE]


def test_cached_signer_is_checked_against_current_keys(tmp_path, read_packages):
    repo_path = _write_repo(
        tmp_path / "repo", {PACKAGE: SIGNED_BY_PLATFORM_KEY}
    )
    exporter = _make_signature_checker(tmp_path, repo_path)
    cache = SignatureCache(tmp_path / "signatures.json", exporter.logger)
    _check(exporter, repo_path, cache)
    _check(exporter, repo_path, cache, key_id=FOREIGN_KEY)

    assert read_packages == [PACKAGE]
    assert f"{PACKAGE} {PLATFORM_KEY}" in _export_errors(exporter)


def test_signature_cache_ignore_cached(tmp_path, read_packages):
    repo_path = _write_repo(
        tmp_path / "repo", {PACKAGE: SIGNED_BY_PLATFORM_KEY}
    )
    exporter = _make_signature_checker(tmp_path, repo_path)
    cache_path = tmp_path / "signatures.json"
    cache = SignatureCache(cache_path, exporter.logger)
    _check(exporter, repo_path, cache)
    cache.save(prune=True)

    cache = SignatureCache(cache_path, exporter.logger, ignore_cached=True)
    _check(exporter, repo_path, cache)

    assert read_packages == [PACKAGE, PACKAGE]


def test_primary_checksums_skip_file_names_of_several_packages(tmp_path):
    other = "bar-2.0-1.el10.noarch.rpm"
    _write_repodata(
        tmp_path,
        [
            _primary_package(PACKAGE, SIGNED_BY_PLATFORM_KEY, 64, epoch="0"),
            _primary_package(PACKAGE, SIGNED_BY_FOREIGN_KEY, 64, epoch="1"),
            _primary_package(other, SIGNED_BY_PLATFORM_KEY, 64),
        ],
    )
    checksums = packages_exporter.load_primary_checksums(str(tmp_path))
    sha256 = hashlib.sha256(SIGNED_BY_PLATFORM_KEY).hexdigest()
    assert checksums == {other: (f"sha256:{sha256}", 64)}


def test_signature_cache_prune(tmp_path):
    logger = logging.getLogger("test-packages-exporter")
    cache_path = tmp_path / "signatures.json"
    cache = SignatureCache(cache_path, logger)
    cache.put("sha256:aa:1", PLATFORM_KEY)
    cache.put("sha256:bb:2", None)
    cache.save(prune=True)

    cache = SignatureCache(cache_path, logger)
    assert cache.get("sha256:bb:2") is None
    cache.save(prune=False)
    cache = SignatureCache(cache_path, logger)
    assert cache.get("sha256:aa:1") == PLATFORM_KEY

    cache = SignatureCache(cache_path, logger)
    assert cache.get("sha256:bb:2") is None
    cache.save(prune=True)
    cache = SignatureCache(cache_path, logger)
    assert cache.get("sha256:aa:1") is packages_exporter.NOT_CACHED
    assert cache.get("sha256:bb:2") is None


def test_signature_cache_survives_corrupted_file(tmp_path):
    cache_path = tmp_path / "signatures.json"
    cache_path.write_text("{not json")
    cache = SignatureCache(cache_path, logging.getLogger("test"))
    assert cache.get("sha256:aa:1") is packages_exporter.NOT_CACHED


class TestRepodataVersionCheck(BaseAsyncTestCase):
    VERSION = "/pulp/api/v3/repositories/rpm/rpm/0001/versions/7/"
    NEWER_VERSION = "/pulp/api/v3/repositories/rpm/rpm/0001/versions/8/"

    async def _export(self, tmp_path, monkeypatch, publications, latest):
        async def noop(*args, **kwargs):
            return None

        async def get_rpm_publications(**kwargs):
            assert kwargs["repository_version_href"] == self.VERSION
            return publications

        async def get_repo_latest_version(repo_href):
            assert repo_href == "/pulp/api/v3/repositories/rpm/rpm/0001/"
            return latest

        monkeypatch.setattr(BasePulpExporter, "download_repodata", noop)
        exporter = _make_exporter()
        exporter.repodata_matches_export = {}
        exporter.pulp_client = SimpleNamespace(
            export_to_filesystem=noop,
            get_rpm_publications=get_rpm_publications,
            get_repo_latest_version=get_repo_latest_version,
        )
        export_path = str(tmp_path / "repo" / "Packages")
        (tmp_path / "repo").mkdir()
        await exporter._export_repository({
            "export_path": export_path,
            "exporter_href": "/exporter/",
            "exporter_name": "repo",
            "repo_latest_version": self.VERSION,
            "repo_url": "https://example.com/repo/",
        })
        return exporter.repodata_matches_export[export_path]

    async def test_published_latest_version(self, tmp_path, monkeypatch):
        assert await self._export(
            tmp_path, monkeypatch, [{"pulp_href": "/p/"}], self.VERSION
        )

    async def test_unpublished_version(self, tmp_path, monkeypatch):
        assert not await self._export(tmp_path, monkeypatch, [], self.VERSION)

    async def test_newer_version_appeared(self, tmp_path, monkeypatch):
        assert not await self._export(
            tmp_path, monkeypatch, [{"pulp_href": "/p/"}], self.NEWER_VERSION
        )
