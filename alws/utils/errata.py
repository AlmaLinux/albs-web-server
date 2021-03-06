import os
import re
import copy
import pathlib
import itertools
from typing import List

import jinja2
import createrepo_c as cr


SCHEMA_VERSION = '1.0'


def debrand_id(rec_id: str) -> str:
    """
    De-brands an RHEL element identifier.
    Args:
        rec_id: OVAL element identifier.
    Returns:
        De-branded OVAL element identifier.
    """
    re_rslt = re.search(
        r"^oval:(?P<org>[-.\w]+?)\."
        r"(?P<advisory>(rh|al)[bes]a):"
        r"(?P<rec_type>[a-z]+):(?P<idx>\d+)$",
        rec_id,
    )
    if not re_rslt:
        raise ValueError(f"invalid OVAL identifier: {rec_id}")
    data = re_rslt.groupdict()
    org = "org.almalinux"
    adv = f'al{data["advisory"][2:]}'
    return f'oval:{org}.{adv}:{data["rec_type"]}:{data["idx"]}'


def debrand_affected_cpe_list(
    cpe_list: List[str], distro_version
) -> List[str]:
    new_list = []
    for cpe in cpe_list:
        cpe = cpe.replace("redhat:enterprise_linux", "almalinux:almalinux")
        if distro_version == "8":
            cpe = cpe.replace("crb", "powertools")
        new_list.append(cpe)
    return new_list


def debrand_reference(ref: dict, distro_version: str) -> dict:
    match = re.search(r"([A-Z]+)-(\d+):(\d+)", ref["id"])
    if not match:
        return ref
    prefix, year, _id = match.groups()
    prefix = re.sub(r"^RH", "AL", prefix)
    suffix = f"{prefix}-{year}-{_id}.html"
    return {
        "id": f"{prefix}-{year}:{_id}",
        "url": f"https://errata.almalinux.org/{distro_version}/{suffix}",
        "source": "ALSA",
    }


def debrand_comment(comment: str, distro_version: str) -> str:
    comment = re.sub(
        r"is signed with Red Hat .*? key",
        f"is signed with AlmaLinux OS {distro_version} key",
        comment,
    )
    comment = comment.replace(
        "Red Hat Enterprise Linux must be installed",
        "AlmaLinux must be installed",
    )
    comment = comment.replace(
        f"Red Hat Enterprise Linux {distro_version} is installed",
        f"AlmaLinux {distro_version} is installed",
    )
    return comment


def find_metadata(repodata_dir, key) -> str:
    repomd = cr.Repomd(os.path.join(repodata_dir, 'repomd.xml'))
    path = next(
        item.location_href
        for item in repomd.records
        if item.type == key
    )
    return os.path.join(repodata_dir, os.path.basename(path))


def iter_updateinfo(filename: str):
    updateinfo = cr.UpdateInfo()
    cr.xml_parse_updateinfo(filename, updateinfo)
    for update in updateinfo.updates:
        yield update


def extract_errata_metadata(update: cr.UpdateInfo) -> dict:
    pkglist = {}
    for item in update.collections:
        pkglist = {
            'name': item.name,
            'shortname': item.shortname,
            'packages': []
        }
        if item.module:
            pkglist['module'] = {
                'stream': item.module.stream,
                'name': item.module.name,
                'version': item.module.version,
                'arch': item.module.arch,
                'context': item.module.context
            }
        for collection in item.packages:
            pkglist['packages'].append({
                'src': collection.src,
                'name': collection.name,
                'epoch': collection.epoch,
                'version': collection.version,
                'release': collection.release,
                'arch': collection.arch,
                'filename': collection.filename,
                'sum': collection.sum,
                'sum_type': collection.sum_type,
                'reboot_suggested': collection.reboot_suggested
            })
    refs = []
    for item in update.references:
        refs.append({
            'href': item.href,
            'type': item.type,
            'id': item.id,
            'title': item.title
        })
    return {
        'updateinfo_id': update.id,
        'issued_date': update.issued_date,
        'fromstr': update.fromstr,
        'title': update.title,
        'type': update.type,
        'release': update.release,
        'version': update.version,
        'rights': update.rights,
        'solution': update.solution,
        'status': update.status,
        'severity': update.severity,
        'summary': update.summary,
        'pushcount': update.pushcount,
        'updated_date': update.updated_date,
        'pkglist': pkglist,
        'description': update.description,
        'references': refs
    }


def _get_module_nsvca(module):
    return ':'.join([
        module['name'],
        module['stream'],
        module['version'],
        module['context'],
        module['arch']
    ])


def extract_errata_metadata_modern(update):
    record = {
        'id': update.id,
        'issued_date': int(update.issued_date.timestamp()),
        'updated_date': int(update.updated_date.timestamp()),
        'severity': update.severity,
        'title': update.title,
        'description': update.description,
        'type': update.type,
        'packages': [],
        'modules': [],
        'references': []
    }
    module_nsvca = None
    for item in update.collections:
        if item.module:
            record['modules'].append({
                'name': item.module.name,
                'arch': item.module.arch,
                'stream': item.module.stream,
                'version': str(item.module.version),
                'context': item.module.context
            })
            module_nsvca = _get_module_nsvca(record['modules'][-1])
        for pkg in item.packages:
            record['packages'].append({
                'name': pkg.name,
                'epoch': pkg.epoch,
                'version': pkg.version,
                'release': pkg.release,
                'arch': pkg.arch,
                'src': pkg.src,
                'filename': pkg.filename,
                'checksum': pkg.sum,
                'checksum_type': cr.checksum_name_str(pkg.sum_type),
                'reboot_suggested': pkg.reboot_suggested
            })
            if module_nsvca:
                record['packages'][-1]['module'] = module_nsvca
        for ref in update.references:
            record['references'].append({
                'id': ref.id,
                'type': ref.type,
                'href': ref.href
            })
    return {
        'schema_version': SCHEMA_VERSION,
        'data': [record]
    }


def merge_errata_records(a, b):
    processed_records = {}
    result = []
    for record in itertools.chain(a, b):
        if record['updateinfo_id'] not in processed_records:
            new_record = copy.deepcopy(record)
            processed_records[new_record['updateinfo_id']] = new_record
            result.append(new_record)
            continue
        processed_packages = set()
        result_record = processed_records[record['updateinfo_id']]
        for pkg in result_record['pkglist']['packages']:
            processed_packages.add(pkg['sum'])
        for pkg in record['pkglist']['packages']:
            if pkg['sum'] in processed_packages:
                continue
            processed_packages.add(pkg['sum'])
            result_record['pkglist']['packages'].append(pkg)
    return result


def merge_errata_records_modern(a, b):
    processed_records = {}
    result = []
    for record in itertools.chain(a['data'], b['data']):
        if record['id'] not in processed_records:
            new_record = copy.deepcopy(record)
            processed_records[new_record['id']] = new_record
            result.append(new_record)
            continue
        processed_packages = set()
        result_record = processed_records[record['id']]
        for pkg in result_record['packages']:
            processed_packages.add(pkg['checksum'])
        for pkg in record['packages']:
            if pkg['checksum'] in processed_packages:
                continue
            processed_packages.add(pkg['checksum'])
            result_record['packages'].append(pkg)
        processed_modules = set()
        for module in result_record['modules']:
            processed_modules.add(_get_module_nsvca(module))
        for module in record['modules']:
            nsvca = _get_module_nsvca(module)
            if nsvca in processed_modules:
                continue
            processed_modules.add(nsvca)
            result_record['modules'].append(module)
    return {
        'schema_version': SCHEMA_VERSION,
        'data': result
    }


def dump_errata_to_html(errata):
    template_dir = pathlib.Path(__file__).absolute().parent / "templates"
    template = (template_dir / "errata_alma_page.j2").read_text()
    return jinja2.Template(template).render(errata=errata)


def generate_errata_page(errata, errata_dir):
    errata_file = '{0}.html'.format(errata['updateinfo_id'].replace(':', '-'))
    errata_path = os.path.join(errata_dir, errata_file)
    with open(errata_path, 'wb') as fd:
        fd.write(dump_errata_to_html(errata).encode('utf-8'))
    return errata_path