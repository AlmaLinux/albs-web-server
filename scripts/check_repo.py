import argparse
import logging 
import os
import xml.etree.ElementTree as ET
import gzip

logger = logging.getLogger('check_repo')



def check_repomd_xml(repo_path, module_repo):
    logger.info('Checking repomd.xml')
    repodata_path = os.path.join(repo_path, 'repodata')
    if not os.path.exists(os.path.join(repodata_path, 'repomd.xml')):
        logger.error('repomd.xml not found')
        return False
    else:
        logger.info('repoxmd.xml found')
    repodata_file = []
    status = True
    tree = ET.parse(os.path.join(repodata_path, 'repomd.xml'))
    root = tree.getroot()
    for child in root:
        if child.attrib:
            for child1 in child:
                if 'location' in child1.tag:
                    repodata_file.append(
                        os.path.join(
                            repodata_path,
                            child1.attrib['href'].replace('repodata/', '')
                        )
                    )
    if module_repo:
        modules_exist = False
    for file in repodata_file:
        if not os.path.exists(file):
            logger.error('File %s not found', file)
            status = False
        if module_repo and 'modules.yaml' in file:
            modules_exist = True
    if module_repo:
        if modules_exist:
            logger.info('File modules.yaml exists')
        else:
            logger.error('File modules.yaml not found')
            status = False
    return status


def get_primary_location(repodata_path):
    primary_filename = ''
    tree = ET.parse(os.path.join(repodata_path, 'repomd.xml'))
    root = tree.getroot()
    for child in root:
        if child.attrib and 'primary' == child.attrib['type']:
            for child1 in child:
                if 'location' in child1.tag:
                    primary_filename = os.path.join(
                        repodata_path,
                        child1.attrib['href'].replace('repodata/', '')
                        )
    return primary_filename


def get_file_list_from_primary(primary_file):
    tree = ET.parse(primary_file)
    root = tree.getroot()
    file_list = []
    for child in root:
        if child.tag == '{http://linux.duke.edu/metadata/common}package':
            for child1 in child:
                if child1.tag == '{http://linux.duke.edu/metadata/common}location':
                    file_list.append(child1.attrib['href'].split('/')[-1])
    return file_list


def get_file_list_from_repodata(repo_path):
    repodata_path = os.path.join(repo_path, 'repodata')
    primary_filename = get_primary_location(repodata_path)
    if primary_filename:
        if not os.path.exists(os.path.join(repodata_path, primary_filename)):
            logger.error('Primary file %s not found!', primary_filename)
            return
        else:
            primary_file = gzip.open(os.path.join(repodata_path, primary_filename), 'rb')
            file_list = get_file_list_from_primary(primary_file)
            return file_list


def get_files_from_disk(repo_path):
    file_list = []
    for root, dirs, files in os.walk(os.path.join(repo_path, 'Packages')):
        for file in files:
            if file.endswith('.rpm'):
                file_list.append(file.split('/')[-1])
    return file_list


def compare_file_lists(
    repodata_files,
    disk_files
):
    status = True
    for file in repodata_files:
        if file not in disk_files:
            logger.error('File %s not found on disk', file)
            status = False
    for file in disk_files:
        if file not in repodata_files:
            logger.error('File %s not found in repodata', file)
            status = False
    return status


def main(repo_path, module_repo, check_files):
    logger.info('Checking repo %s', repo_path)
    metadata_files = get_file_list_from_repodata(repo_path)
    if not check_repomd_xml(repo_path, module_repo):
        exit(1)
    disk_files = get_files_from_disk(repo_path)
    if check_files:
        if compare_file_lists(metadata_files, disk_files):
            logger.info('All files in repo %s are OK', repo_path)
        else:
            logger.error('All files in repo %s are not OK', repo_path)
            exit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--repo',
        '-r',
        dest='repo',
        help='Path to the repository',
        required=True
    )
    parser.add_argument(
        '--module_repo',
        dest='module',
        help='Flag to set if the repo is a module repo',
        action='store_true',
        default=False
    )
    parser.add_argument(
        '--check_files',
        dest='check_files',
        help='Flag to check if all files are present',
        action='store_true',
        default=False
    )
    parser.add_argument(
        '--logs',
        dest='logs',
        help='Show logs',
        action='store_true',
        default=False
    )
    args = parser.parse_args()
    if args.logs:
            logging.basicConfig(
            level=logging.INFO,
            handlers=[
                logging.StreamHandler(),
            ],
        )
    else:
        logging.disable(logging.CRITICAL)
    main(args.repo, args.module, args.check_files)
