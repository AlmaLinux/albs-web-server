import tempfile
import typing

import createrepo_c as cr
from errata2osv import errata_to_osv


def generate_updaterecord(
    record_dict: typing.Dict[str, typing.Any],
) -> cr.UpdateRecord:
    cr_rec = cr.UpdateRecord()
    cr_col = cr.UpdateCollection()
    cr_rec.id = record_dict["updateinfo_id"]
    for key in (
        "issued_date",
        "pushcount",
        "release",
        "rights",
        "severity",
        "summary",
        "title",
        "description",
        "fromstr",
        "type",
        "status",
        "version",
        "rights",
        "updated_date",
    ):
        if key in record_dict:
            setattr(cr_rec, key, record_dict[key])
    cr_rec.solution = record_dict["solution"] or ""
    for ref in record_dict.get("references", []):
        cr_ref = cr.UpdateReference()
        for key in (
            "href",
            "type",
            "id",
            "title",
        ):
            setattr(cr_ref, key, ref[key])
        cr_rec.append_reference(cr_ref)
    pkglist = record_dict["pkglist"]
    cr_col.name = pkglist["name"]
    cr_col.name = pkglist["shortname"]
    col_module = pkglist.get("module", {})
    if col_module:
        cr_mod = cr.UpdateCollectionModule()
        for key in (
            "stream",
            "name",
            "version",
            "arch",
            "context",
        ):
            setattr(cr_mod, key, col_module[key])
        cr_col.module = cr_mod
    for package in pkglist["packages"]:
        cr_pkg = cr.UpdateCollectionPackage()
        for key in (
            "name",
            "src",
            "version",
            "release",
            "arch",
            "filename",
            "sum",
            "epoch",
            "reboot_suggested",
            "sum_type",
        ):
            setattr(cr_pkg, key, package[key])
        cr_col.append(cr_pkg)
    cr_rec.append_collection(cr_col)
    return cr_rec


def export_errata_to_osv(
    errata_records: typing.List[typing.Dict[str, typing.Any]],
    target_dir: str,
    ecosystem: str,
):
    with tempfile.NamedTemporaryFile(suffix="updateinfo.xml") as fd:
        updateinfo = cr.UpdateInfo()
        for record in errata_records:
            updateinfo.append(generate_updaterecord(record))
        fd.write(updateinfo.xml_dump().encode())
        fd.flush()
        errata_to_osv(
            updateinfo=fd.name,
            target_dir=target_dir,
            ecosystem=ecosystem,
        )
