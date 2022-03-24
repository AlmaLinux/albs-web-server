import os
import re
import gzip
import argparse
import binascii

import createrepo_c as cr

from alws.utils.modularity import IndexWrapper


UPDATE_RECORD_FIELDS = (
    'id', 'description', 'fromstr', 'issued_date', 'pushcount',
    'reboot_suggested', 'release', 'rights', 'severity', 'solution',
    'status', 'summary', 'title', 'type', 'updated_date', 'version'
)


def checksum_type_to_cr(sum_type: str) -> int:
    return {
        'sha': cr.SHA,
        'sha1': cr.SHA1,
        'sha224': cr.SHA224,
        'sha256': cr.SHA256,
        'sha384': cr.SHA384,
        'sha512': cr.SHA512
    }[sum_type]


def remove_module_release(release: str) -> str:
    return re.sub(r'\.module.*$', '', release)


def is_gzip_file(file_path: str) -> bool:
    with open(file_path, 'rb') as fd:
        return binascii.hexlify(fd.read(2)) == b'1f8b'


class PackagesCache:

    def __init__(self, repodata_dir: str):
        self.packages_cache = {}
        self.modules_cache = {}
        self._load_packages_cache(repodata_dir)
        self._load_modules_cache(repodata_dir)

    @staticmethod
    def find_metadata(repodata_dir, key) -> str:
        repomd = cr.Repomd(os.path.join(repodata_dir, 'repomd.xml'))
        path = next(
            item.location_href
            for item in repomd.records
            if item.type == key
        )
        return os.path.join(repodata_dir, os.path.basename(path))

    def _load_packages_cache(self, repodata_dir: str):
        def pkgcb(pkg):
            key = (
                pkg.name,
                pkg.version,
                remove_module_release(pkg.release),
            )
            self.packages_cache[key] = {
                'name': pkg.name,
                'epoch': pkg.epoch,
                'version': pkg.version,
                'release': pkg.release,
                'arch': pkg.arch,
                'sourcerpm': pkg.rpm_sourcerpm,
                'location': os.path.basename(pkg.location_href),
                'sha256_checksum': pkg.pkgId,
                'checksum_type': pkg.checksum_type
            }

        primary_path = self.find_metadata(repodata_dir, 'primary')
        cr.xml_parse_primary(primary_path, pkgcb=pkgcb, do_files=0)

    def _load_modules_cache(self, repodata_dir: str):
        try:
            modules_yaml = self.find_metadata(repodata_dir, 'modules')
        except StopIteration:
            return
        file_open = open
        if is_gzip_file(modules_yaml):
            file_open = gzip.open
        with file_open(modules_yaml, 'rb') as fd:
            modular_index = IndexWrapper.from_template(fd.read().decode('utf-8'))
        for module in modular_index.iter_modules():
            key = (module.name, module.stream)
            self.modules_cache[key] = module

    def modify_record(self, record: cr.UpdateRecord):
        rpm_packages = []
        module = None
        collection = record.collections[0]
        for package in collection.packages:
            key = (
                package.name,
                package.version,
                remove_module_release(package.release)
            )
            ppc_package = self.packages_cache.get(key)
            if ppc_package:
                rpm_packages.append((package, ppc_package))
        if not rpm_packages:
            return
        if collection.module:
            module = self.modules_cache.get((
                collection.module.name,
                collection.module.stream
            ))
        new_record = cr.UpdateRecord()
        for key in UPDATE_RECORD_FIELDS:
            setattr(new_record, key, getattr(record, key))

        for ref in record.references:
            new_ref = cr.UpdateReference()
            for key in ('href', 'id', 'title', 'type'):
                setattr(new_ref, key, getattr(ref, key))
            new_record.append_reference(new_ref)

        new_collection = cr.UpdateCollection()
        for key in ('name', 'shortname'):
            setattr(
                new_collection,
                key,
                getattr(collection, key).replace('x86_64', 'ppc64le')
            )
        for package, cache_pkg in rpm_packages:
            new_package = cr.UpdateCollectionPackage()
            new_package.name = cache_pkg['name']
            new_package.epoch = cache_pkg['epoch']
            new_package.version = cache_pkg['version']
            new_package.release = cache_pkg['release']
            new_package.arch = cache_pkg['arch']
            new_package.src = cache_pkg['sourcerpm']
            new_package.sum = cache_pkg['sha256_checksum']
            new_package.sum_type = checksum_type_to_cr(
                cache_pkg['checksum_type']
            )
            new_package.filename = cache_pkg['location']
            new_package.relogin_suggested = package.relogin_suggested
            new_package.restart_suggested = package.restart_suggested
            new_collection.append(new_package)
        if module:
            cr_module = cr.UpdateCollectionModule()
            cr_module.name = module.name
            cr_module.stream = module.stream
            cr_module.version = module.version
            cr_module.context = module.context
            new_collection.module = cr_module
        new_record.append_collection(new_collection)
        return new_record


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('input', help='input updateinfo.xml')
    parser.add_argument('output', help='output updateinfo.xml')
    parser.add_argument('repodata', help='directory to repodata files')
    return parser.parse_args()


def iter_updateinfo(filename: str):
    updateinfo = cr.UpdateInfo()
    cr.xml_parse_updateinfo(filename, updateinfo)
    for update in updateinfo.updates:
        yield update


def append_record(
    updateinfo: cr.UpdateInfo,
    packages_cache: PackagesCache,
    record: cr.UpdateRecord
):
    updated_record = packages_cache.modify_record(record)
    if updated_record:
        updateinfo.append(updated_record)


def update_updateinfo(input_file: str, repodata_dir: str, output_file: str):
    output_updateinfo = cr.UpdateInfo()
    packages_cache = PackagesCache(repodata_dir)
    for record in iter_updateinfo(input_file):
        append_record(output_updateinfo, packages_cache, record)
    with open(output_file, 'w') as fd:
        fd.write(output_updateinfo.xml_dump())


def main():
    cli = parse_args()
    input_file = cli.input
    output_file = cli.output
    repodata_dir = cli.repodata
    update_updateinfo(input_file, repodata_dir, output_file)


if __name__ == '__main__':
    main()
