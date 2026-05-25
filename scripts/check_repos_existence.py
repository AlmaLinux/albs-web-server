#!/usr/bin/env python3
"""Check that every remote_url in a reference_data YAML is reachable."""
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import yaml


def collect_repos(data):
    repos = []
    for platform in data:
        for repo in platform.get('repositories', []) or []:
            url = repo.get('remote_url')
            if url:
                repos.append((repo.get('name', '?'), repo.get('arch', '?'), url))
    return repos


def check(url, timeout=15):
    try:
        r = requests.head(url, allow_redirects=True, timeout=timeout)
        if r.status_code in (405, 403):
            r = requests.get(url, stream=True, timeout=timeout)
        return r.status_code
    except requests.RequestException as e:
        return f'ERR: {e.__class__.__name__}'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('yaml_file')
    parser.add_argument('--workers', type=int, default=16)
    args = parser.parse_args()

    with open(args.yaml_file) as f:
        data = yaml.safe_load(f)

    repos = collect_repos(data)
    print(f'Checking {len(repos)} repositories...\n')

    missing = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(check, url): (name, arch, url) for name, arch, url in repos}
        for fut in as_completed(futures):
            name, arch, url = futures[fut]
            status = fut.result()
            ok = status == 200
            marker = 'OK ' if ok else 'BAD'
            print(f'[{marker}] {status} {arch:10s} {name:40s} {url}')
            if not ok:
                missing.append((name, arch, url, status))

    print(f'\n{len(missing)} unreachable repos:')
    for name, arch, url, status in missing:
        print(f'  {status} {arch} {name} {url}')

    sys.exit(1 if missing else 0)


if __name__ == '__main__':
    main()
