import asyncio
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import createrepo_c as cr
import pytest

from scripts.exporters import packages_exporter
from scripts.exporters.base_exporter import BasePulpExporter, ExportState
from scripts.exporters.packages_exporter import (
    ErrataPageCache,
    PackagesExporter,
    SignatureCache,
    extract_errata_from_exported_paths,
    generate_errata_pages,
    sign_repodata,
    start_oval_requests,
)
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
        exporter.skip_unchanged = False
        exporter.exported_versions = {}
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


def test_platform_sign_key_ignores_keys_without_platforms():
    db_sign_keys = [
        {"keyid": "AAAA", "platform_ids": None},
        {"keyid": "BBBB"},
        {"keyid": "CCCC", "platform_ids": [1]},
    ]
    assert packages_exporter.get_platform_sign_key_id(db_sign_keys, 1) == "CCCC"
    assert packages_exporter.get_platform_sign_key_id(db_sign_keys, 2) is None


def test_export_state_roundtrip(tmp_path):
    logger = logging.getLogger("test-packages-exporter")
    state_path = tmp_path / "export_state.json"
    state = ExportState(state_path, logger)
    assert not state.matches("/repo/Packages", "/v/1/", "hardlink")

    state.mark("/repo/Packages", "/v/1/", "hardlink")
    state.save()

    state = ExportState(state_path, logger)
    assert state.matches("/repo/Packages", "/v/1/", "hardlink")
    assert not state.matches("/repo/Packages", "/v/2/", "hardlink")
    assert not state.matches("/repo/Packages", "/v/1/", "symlink")
    assert not state.matches("/other/Packages", "/v/1/", "hardlink")


def test_export_state_survives_corrupted_file(tmp_path):
    state_path = tmp_path / "export_state.json"
    state_path.write_text("{not json")
    state = ExportState(state_path, logging.getLogger("test"))
    assert not state.matches("/repo/Packages", "/v/1/", "hardlink")
    state.save()
    assert ExportState(state_path, logging.getLogger("test")) is not None


class TestSkipUnchangedExport(BaseAsyncTestCase):
    """
    A repository is exported from Pulp again only when its version
    changed since the last complete export, or it went missing on the
    filesystem, or the export is forced.
    """

    REPO_HREF = "/pulp/api/v3/repositories/rpm/rpm/0001/"
    VERSION = REPO_HREF + "versions/7/"
    NEWER_VERSION = REPO_HREF + "versions/8/"

    def _make(self, tmp_path, monkeypatch, skip_unchanged=True):
        pulp_exports = []

        async def export_to_filesystem(href, version):
            pulp_exports.append(version)
            return {"state": "completed"}

        async def get_rpm_publications(**kwargs):
            return [{"pulp_href": "/p/"}]

        async def get_repo_latest_version(repo_href):
            return self.latest_version

        async def noop(*args, **kwargs):
            return None

        monkeypatch.setattr(BasePulpExporter, "download_repodata", noop)
        exporter = _make_exporter()
        exporter.export_method = "hardlink"
        exporter.skip_unchanged = skip_unchanged
        exporter.repodata_matches_export = {}
        exporter.unchanged_export_paths = set()
        exporter.exported_versions = {}
        exporter.export_state = ExportState(
            tmp_path / "export_state.json", exporter.logger
        )
        exporter.pulp_client = SimpleNamespace(
            export_to_filesystem=export_to_filesystem,
            get_rpm_publications=get_rpm_publications,
            get_repo_latest_version=get_repo_latest_version,
        )
        return exporter, pulp_exports

    async def _export(self, exporter, tmp_path, version):
        self.latest_version = version
        export_path = str(tmp_path / "repo" / "Packages")
        (tmp_path / "repo").mkdir(exist_ok=True)
        result = await exporter._export_repository({
            "export_path": export_path,
            "exporter_href": "/exporter/",
            "exporter_name": "repo",
            "repo_latest_version": version,
            "repo_url": "https://example.com/repo/",
        })
        assert result == export_path
        return export_path

    @staticmethod
    def _complete_export(exporter, export_path):
        # What Pulp, createrepo_c and the sign server leave behind
        packages_dir = Path(export_path)
        packages_dir.mkdir(exist_ok=True)
        repodata = packages_dir.parent / "repodata"
        repodata.mkdir(exist_ok=True)
        (repodata / "repomd.xml").write_text("<repomd/>")
        (repodata / "repomd.xml.asc").write_text(FAKE_SIGNATURE)
        exporter.mark_exported(export_path)

    async def test_unchanged_repository_is_skipped(self, tmp_path, monkeypatch):
        exporter, pulp_exports = self._make(tmp_path, monkeypatch)
        export_path = await self._export(exporter, tmp_path, self.VERSION)
        assert pulp_exports == [self.VERSION]
        assert not exporter.is_unchanged(export_path)
        self._complete_export(exporter, export_path)

        await self._export(exporter, tmp_path, self.VERSION)
        assert pulp_exports == [self.VERSION]
        assert exporter.is_unchanged(export_path)
        assert exporter.repodata_matches_export[export_path]

    async def test_incomplete_export_is_repeated(self, tmp_path, monkeypatch):
        exporter, pulp_exports = self._make(tmp_path, monkeypatch)
        export_path = await self._export(exporter, tmp_path, self.VERSION)
        # Not marked: post-processing or signing failed
        Path(export_path).mkdir()

        await self._export(exporter, tmp_path, self.VERSION)
        assert pulp_exports == [self.VERSION, self.VERSION]
        assert not exporter.is_unchanged(export_path)

    async def test_missing_repository_is_exported_again(
        self, tmp_path, monkeypatch
    ):
        exporter, pulp_exports = self._make(tmp_path, monkeypatch)
        export_path = await self._export(exporter, tmp_path, self.VERSION)
        self._complete_export(exporter, export_path)

        Path(export_path).rmdir()
        await self._export(exporter, tmp_path, self.VERSION)
        assert pulp_exports == [self.VERSION, self.VERSION]
        assert not exporter.is_unchanged(export_path)

    async def test_missing_repodata_is_exported_again(
        self, tmp_path, monkeypatch
    ):
        exporter, pulp_exports = self._make(tmp_path, monkeypatch)
        export_path = await self._export(exporter, tmp_path, self.VERSION)
        self._complete_export(exporter, export_path)

        (Path(export_path).parent / "repodata" / "repomd.xml").unlink()
        await self._export(exporter, tmp_path, self.VERSION)
        assert pulp_exports == [self.VERSION, self.VERSION]

    async def test_new_version_is_exported(self, tmp_path, monkeypatch):
        exporter, pulp_exports = self._make(tmp_path, monkeypatch)
        export_path = await self._export(exporter, tmp_path, self.VERSION)
        self._complete_export(exporter, export_path)

        await self._export(exporter, tmp_path, self.NEWER_VERSION)
        assert pulp_exports == [self.VERSION, self.NEWER_VERSION]
        assert not exporter.is_unchanged(export_path)

    async def test_other_export_method_is_exported(
        self, tmp_path, monkeypatch
    ):
        exporter, pulp_exports = self._make(tmp_path, monkeypatch)
        export_path = await self._export(exporter, tmp_path, self.VERSION)
        self._complete_export(exporter, export_path)

        exporter.export_method = "symlink"
        await self._export(exporter, tmp_path, self.VERSION)
        assert pulp_exports == [self.VERSION, self.VERSION]

    async def test_forced_export(self, tmp_path, monkeypatch):
        exporter, pulp_exports = self._make(
            tmp_path, monkeypatch, skip_unchanged=False
        )
        export_path = await self._export(exporter, tmp_path, self.VERSION)
        self._complete_export(exporter, export_path)

        await self._export(exporter, tmp_path, self.VERSION)
        assert pulp_exports == [self.VERSION, self.VERSION]
        assert not exporter.is_unchanged(export_path)


class TestSignRepodataOfUnchangedRepositories(BaseAsyncTestCase):
    KEY_ID = "1234567890ABCDEF"

    def _make(self, monkeypatch, tmp_path):
        signed = []

        async def fake_make_request(self, method, endpoint, **kwargs):
            if endpoint == "token":
                return {"token": "test-token"}
            if endpoint == "sign":
                signed.append(kwargs["params"]["keyid"])
                return FAKE_SIGNATURE
            raise AssertionError(f"unexpected endpoint {endpoint!r}")

        monkeypatch.setattr(BasePulpExporter, "make_request", fake_make_request)
        exporter = _make_exporter()
        exporter.unchanged_export_paths = set()
        repos = {}
        for name in ("changed", "unchanged", "unchanged-unsigned"):
            repo_dir = tmp_path / name
            (repo_dir / "Packages").mkdir(parents=True)
            (repo_dir / "repodata").mkdir()
            (repo_dir / "repodata" / "repomd.xml").write_text("<repomd/>")
            repos[name] = str(repo_dir / "Packages")
        (tmp_path / "unchanged" / "repodata" / "repomd.xml.asc").write_text(
            FAKE_SIGNATURE
        )
        exporter.unchanged_export_paths = {
            repos["unchanged"],
            repos["unchanged-unsigned"],
        }
        return exporter, repos, signed

    async def test_already_signed_repodata_is_kept(self, monkeypatch, tmp_path):
        exporter, repos, signed = self._make(monkeypatch, tmp_path)
        signed_paths = await sign_repodata(
            exporter,
            list(repos.values()),
            platforms_dict={},
            db_sign_keys=[],
            override_key_id=self.KEY_ID,
        )
        # Only the changed one and the unchanged one that lost its
        # signature are signed, but all of them are complete
        assert signed == [self.KEY_ID, self.KEY_ID]
        assert signed_paths == set(repos.values())
        for repo_path in repos.values():
            asc = Path(repo_path).parent / "repodata" / "repomd.xml.asc"
            assert asc.read_text() == FAKE_SIGNATURE

    async def test_failed_signing_is_reported(self, monkeypatch, tmp_path):
        exporter, repos, _ = self._make(monkeypatch, tmp_path)

        async def failing_sign(self, path_to_file, key_id, token, **kwargs):
            return {"asc_content": None, "error": "boom"}

        monkeypatch.setattr(BasePulpExporter, "sign_repomd_xml", failing_sign)
        signed_paths = await sign_repodata(
            exporter,
            list(repos.values()),
            platforms_dict={},
            db_sign_keys=[],
            override_key_id=self.KEY_ID,
        )
        assert signed_paths == {repos["unchanged"]}

    async def test_missing_key_counts_as_complete(self, monkeypatch, tmp_path):
        exporter, repos, signed = self._make(monkeypatch, tmp_path)
        signed_paths = await sign_repodata(
            exporter,
            [repos["changed"]],
            platforms_dict={},
            db_sign_keys=[],
        )
        assert signed == []
        assert signed_paths == {repos["changed"]}


def _make_erratum(updateinfo_id: str, **overrides) -> dict:
    record = {
        "updateinfo_id": updateinfo_id,
        "title": "foo security update",
        "type": "security",
        "severity": "Moderate",
        "description": "Fixes CVE-2024-0001",
        "issued_date": datetime(2024, 1, 2, tzinfo=timezone.utc),
        "updated_date": datetime(2024, 1, 3, tzinfo=timezone.utc),
        "references": [
            {
                "href": "https://errata.almalinux.org/8/ALSA-2024-0001.html",
                "type": "self",
                "id": updateinfo_id,
                "title": updateinfo_id,
            }
        ],
        "pkglist": {
            "name": "AlmaLinux-8",
            "shortname": "AlmaLinux-8",
            "packages": [
                {"arch": "x86_64", "filename": PACKAGE, "sum": "bb"},
                {"arch": "aarch64", "filename": PACKAGE, "sum": "aa"},
            ],
        },
    }
    record.update(overrides)
    return record


def _make_page_exporter(tmp_path, skip_unchanged=True) -> PackagesExporter:
    exporter = _make_exporter()
    exporter.repodata_cache_dir = tmp_path / "cache"
    exporter.skip_unchanged = skip_unchanged
    return exporter


class TestErrataPagesCache:
    PLATFORM = "AlmaLinux-8"

    def _generate(self, tmp_path, errata, skip_unchanged=True):
        html_path = tmp_path / "html"
        html_path.mkdir(exist_ok=True)
        exporter = _make_page_exporter(tmp_path, skip_unchanged)
        generated = generate_errata_pages(
            exporter, errata, str(html_path), self.PLATFORM
        )
        return generated, html_path

    def test_unchanged_pages_are_kept(self, tmp_path):
        errata = [
            _make_erratum("ALSA-2024:0001"),
            _make_erratum("ALSA-2024:0002"),
        ]
        generated, html_path = self._generate(tmp_path, errata)
        assert generated == 2
        page = html_path / "ALSA-2024-0001.html"
        assert "CVE-2024-0001" in page.read_text()
        page.write_text("stale")

        generated, _ = self._generate(tmp_path, errata)
        assert generated == 0
        assert page.read_text() == "stale"

    def test_packages_are_sorted_by_arch_when_page_is_kept(self, tmp_path):
        errata = [_make_erratum("ALSA-2024:0001")]
        self._generate(tmp_path, errata)
        errata = [_make_erratum("ALSA-2024:0001")]
        generated, _ = self._generate(tmp_path, errata)
        assert generated == 0
        arches = [pkg["arch"] for pkg in errata[0]["pkglist"]["packages"]]
        assert arches == ["aarch64", "x86_64"]

    def test_changed_erratum_is_written_again(self, tmp_path):
        errata = [_make_erratum("ALSA-2024:0001")]
        self._generate(tmp_path, errata)
        errata[0]["pkglist"]["packages"].append(
            {"arch": "ppc64le", "filename": PACKAGE, "sum": "cc"}
        )
        generated, html_path = self._generate(tmp_path, errata)
        assert generated == 1
        assert "ppc64le" in (html_path / "ALSA-2024-0001.html").read_text()

    def test_missing_page_is_written_again(self, tmp_path):
        errata = [_make_erratum("ALSA-2024:0001")]
        _, html_path = self._generate(tmp_path, errata)
        (html_path / "ALSA-2024-0001.html").unlink()
        generated, _ = self._generate(tmp_path, errata)
        assert generated == 1
        assert (html_path / "ALSA-2024-0001.html").is_file()

    def test_template_change_writes_every_page_again(
        self, tmp_path, monkeypatch
    ):
        errata = [
            _make_erratum("ALSA-2024:0001"),
            _make_erratum("ALSA-2024:0002"),
        ]
        self._generate(tmp_path, errata)
        monkeypatch.setattr(
            packages_exporter,
            "errata_page_template_source",
            lambda: "<html>{{ errata['updateinfo_id'] }}</html>",
        )
        generated, _ = self._generate(tmp_path, errata)
        assert generated == 2

    def test_forced_export_writes_every_page_again(self, tmp_path):
        errata = [_make_erratum("ALSA-2024:0001")]
        _, html_path = self._generate(tmp_path, errata)
        page = html_path / "ALSA-2024-0001.html"
        page.write_text("stale")
        generated, _ = self._generate(tmp_path, errata, skip_unchanged=False)
        assert generated == 1
        assert page.read_text() != "stale"

    def test_cache_survives_corrupted_file(self, tmp_path):
        errata = [_make_erratum("ALSA-2024:0001")]
        self._generate(tmp_path, errata)
        cache_path = (
            tmp_path / "cache" / "errata_pages" / f"{self.PLATFORM}.json"
        )
        assert cache_path.is_file()
        cache_path.write_text("{not json")
        generated, _ = self._generate(tmp_path, errata)
        assert generated == 1

    def test_pages_of_other_platforms_are_not_mixed(self, tmp_path):
        errata = [_make_erratum("ALSA-2024:0001")]
        self._generate(tmp_path, errata)
        html_path = tmp_path / "html9"
        html_path.mkdir()
        exporter = _make_page_exporter(tmp_path)
        generated = generate_errata_pages(
            exporter, errata, str(html_path), "AlmaLinux-9"
        )
        assert generated == 1


def test_errata_page_cache_fingerprint_is_stable():
    first = ErrataPageCache.fingerprint(_make_erratum("ALSA-2024:0001"))
    second = ErrataPageCache.fingerprint(_make_erratum("ALSA-2024:0001"))
    changed = ErrataPageCache.fingerprint(
        _make_erratum("ALSA-2024:0001", severity="Important")
    )
    assert first == second
    assert first != changed


def test_oval_requests_run_in_the_background(monkeypatch):
    requested = []

    async def fake_get_oval_xml(self, platform_name, only_released=False):
        requested.append((platform_name, only_released))
        await asyncio.sleep(0)
        return f"<oval>{platform_name}</oval>"

    monkeypatch.setattr(PackagesExporter, "get_oval_xml", fake_get_oval_xml)
    exporter = _make_exporter()
    futures = start_oval_requests(exporter, ["AlmaLinux-8", "AlmaLinux-9"])
    for platform in ("AlmaLinux-8", "AlmaLinux-9"):
        oval = futures[platform].result(timeout=10)
        assert oval == f"<oval>{platform}</oval>"
    assert sorted(requested) == [("AlmaLinux-8", True), ("AlmaLinux-9", True)]
    assert start_oval_requests(exporter, None) == {}


def test_oval_request_failure_is_raised_when_collected(monkeypatch):
    async def failing_get_oval_xml(self, platform_name, only_released=False):
        raise RuntimeError("web server is down")

    monkeypatch.setattr(PackagesExporter, "get_oval_xml", failing_get_oval_xml)
    futures = start_oval_requests(_make_exporter(), ["AlmaLinux-8"])
    with pytest.raises(RuntimeError, match="web server is down"):
        futures["AlmaLinux-8"].result(timeout=10)


class TestSignatureCheckOfUnchangedRepositories:
    def _make(self, tmp_path, monkeypatch, unchanged, full_check=False):
        checked = []

        def fake_check(self, repository_path, sign_keys, signature_cache):
            checked.append(repository_path)
            signature_cache.put(f"sha256:{repository_path}:1", PLATFORM_KEY)

        async def fake_export_repositories(self, repo_ids, on_exported=None):
            for repo_path in repo_ids:
                if on_exported is not None:
                    await on_exported(repo_path)
            return list(repo_ids)

        monkeypatch.setattr(
            PackagesExporter, "check_rpms_signature", fake_check
        )
        # The paths stand in for the repository ids
        monkeypatch.setattr(
            PackagesExporter, "export_repositories", fake_export_repositories
        )
        exporter = _make_exporter()
        exporter.repodata_cache_dir = tmp_path / "cache"
        exporter.full_signature_check = full_check
        exporter.unchanged_export_paths = set(unchanged)
        repos = []
        for name in ("changed", "unchanged"):
            repo_path = tmp_path / name / "Packages"
            repo_path.mkdir(parents=True)
            repos.append(str(repo_path))
        return exporter, repos, checked

    @pytest.mark.anyio
    async def test_unchanged_repository_is_not_checked(
        self, tmp_path, monkeypatch
    ):
        unchanged = str(tmp_path / "unchanged" / "Packages")
        exporter, repos, checked = self._make(
            tmp_path, monkeypatch, [unchanged]
        )
        exported = await exporter.export_and_check_signatures(
            "AlmaLinux-9", repos, []
        )
        assert exported == repos
        assert checked == [str(tmp_path / "changed" / "Packages")]

    @pytest.mark.anyio
    async def test_full_check_covers_unchanged_repository(
        self, tmp_path, monkeypatch
    ):
        unchanged = str(tmp_path / "unchanged" / "Packages")
        exporter, repos, checked = self._make(
            tmp_path, monkeypatch, [unchanged], full_check=True
        )
        await exporter.export_and_check_signatures("AlmaLinux-9", repos, [])
        assert sorted(checked) == sorted(repos)

    @pytest.mark.anyio
    async def test_cache_is_not_pruned_when_a_repository_is_skipped(
        self, tmp_path, monkeypatch
    ):
        exporter, repos, _ = self._make(tmp_path, monkeypatch, [])
        await exporter.export_and_check_signatures("AlmaLinux-9", repos, [])
        cache_path = tmp_path / "cache" / "signatures" / "AlmaLinux-9.json"
        unchanged_key = f"sha256:{repos[1]}:1"

        exporter.unchanged_export_paths = {repos[1]}
        await exporter.export_and_check_signatures("AlmaLinux-9", repos, [])
        cache = SignatureCache(cache_path, exporter.logger)
        assert cache.get(unchanged_key) == PLATFORM_KEY

        exporter.unchanged_export_paths = set()
        await exporter.export_and_check_signatures(
            "AlmaLinux-9", repos[:1], [], partial=True
        )
        cache = SignatureCache(cache_path, exporter.logger)
        assert cache.get(unchanged_key) == PLATFORM_KEY

        await exporter.export_and_check_signatures("AlmaLinux-9", repos[:1], [])
        cache = SignatureCache(cache_path, exporter.logger)
        assert cache.get(unchanged_key) is packages_exporter.NOT_CACHED


@pytest.mark.anyio
async def test_signatures_are_checked_while_other_repositories_are_exported(
    tmp_path, monkeypatch
):
    events = []
    repos = {}
    for name in ("fast", "slow"):
        repo_path = tmp_path / name / "Packages"
        repo_path.mkdir(parents=True)
        repos[name] = str(repo_path)

    async def fake_create_filesystem_exporters(self, repo_ids):
        return [{"export_path": repos[name]} for name in repo_ids]

    async def fake_export_repository(self, exporter):
        if exporter["export_path"] == repos["slow"]:
            await asyncio.sleep(0.3)
        events.append(("exported", exporter["export_path"]))
        return exporter["export_path"]

    def fake_check(self, repository_path, sign_keys, signature_cache):
        events.append(("checked", repository_path))

    monkeypatch.setattr(
        BasePulpExporter,
        "create_filesystem_exporters",
        fake_create_filesystem_exporters,
    )
    monkeypatch.setattr(
        BasePulpExporter, "_export_repository", fake_export_repository
    )
    monkeypatch.setattr(PackagesExporter, "check_rpms_signature", fake_check)
    exporter = _make_exporter()
    exporter.repodata_cache_dir = tmp_path / "cache"
    exporter.full_signature_check = False
    exporter.unchanged_export_paths = set()

    exported = await exporter.export_and_check_signatures(
        "AlmaLinux-9", ["fast", "slow"], []
    )
    assert sorted(exported) == sorted(repos.values())
    assert events == [
        ("exported", repos["fast"]),
        ("checked", repos["fast"]),
        ("exported", repos["slow"]),
        ("checked", repos["slow"]),
    ]


def test_errata_records_are_merged_in_a_fixed_order(monkeypatch):
    import time

    paths = [
        "/exports/almalinux/9/AppStream/x86_64/os/Packages",
        "/exports/almalinux/9/AppStream/aarch64/os/Packages",
        "/exports/almalinux/9/AppStream/ppc64le/os/Packages",
    ]

    def fake_extract(repo_path):
        # The alphabetically first repository finishes last
        if "aarch64" in repo_path:
            time.sleep(0.2)
        arch = repo_path.split("/")[-3]
        record = _make_erratum(
            "ALSA-2024:0001",
            pkglist={
                "name": f"almalinux-9-for-{arch}-appstream-rpms",
                "shortname": arch,
                "packages": [
                    {"arch": arch, "filename": PACKAGE, "sum": arch}
                ],
            },
        )
        modern = {
            "id": "ALSA-2024:0001",
            "packages": [{"checksum": arch}],
            "references": [],
            "modules": [{
                "name": "foo",
                "stream": "1",
                "version": "1",
                "context": "c",
                "arch": arch,
            }],
        }
        return [record], [modern]

    monkeypatch.setattr(packages_exporter, "extract_errata", fake_extract)
    cache = extract_errata_from_exported_paths(_make_exporter(), paths)
    record = cache["AlmaLinux-9"]["cache"][0]
    assert record["pkglist"]["name"] == (
        "almalinux-9-for-aarch64-appstream-rpms"
    )
    assert [p["sum"] for p in record["pkglist"]["packages"]] == [
        "aarch64", "ppc64le", "x86_64"
    ]
    modern = cache["AlmaLinux-9"]["modern_cache"]["data"][0]
    assert [m["arch"] for m in modern["modules"]] == [
        "aarch64", "ppc64le", "x86_64"
    ]
