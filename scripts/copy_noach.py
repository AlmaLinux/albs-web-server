import asyncio
import logging

from alws.utils.pulp_client import PulpClient

async def copy_rep(client:PulpClient, name):
    rep_x86_64 = await client.get_rpm_repository(name)
    str_x86_64 = rep_x86_64['pulp_href']
    rep_ppc64le = await client.get_rpm_repository(name.replace('x86_64', 'ppc64le'))
    str_ppc64le = rep_ppc64le['pulp_href']
    # Get packages x86_66
    dict_rep_x86_64 = await client.make_get_request('/pulp/api/v3/content/rpm/packages/',
                                               params={'arch': 'noarch',
                                                       'fields': ['name', 'sha256', 'pulp_href'],
                                                       'repository_version': await client.get_repo_latest_version(
                                                       str_x86_64)
                                                    })
    rep_x86_64 = dict_rep_x86_64['results']
    page = dict_rep_x86_64.get('next')
    while page is not None:
        dict_rep_x86_64 = await client.make_get_request(page)
        rep_x86_64 += dict_rep_x86_64['results']
        page = dict_rep_x86_64.get('next')

    # Get packages ppc64le
    dict_rep_ppc64le = await client.make_get_request('/pulp/api/v3/content/rpm/packages/',
                                                params={'fields': ['name', 'sha256', 'pulp_href'],
                                                        'arch': 'noarch',
                                                        'repository_version': await client.get_repo_latest_version(
                                                        str_ppc64le)
                                                        })
    rep_ppc64le = dict_rep_ppc64le['results']
    page = dict_rep_ppc64le.get('next')
    while page is not None:
        dict_rep_ppc64le = await client.make_get_request(page)
        rep_ppc64le += dict_rep_ppc64le['results']
        page = dict_rep_ppc64le.get('next')
    # compare packages
    r_x86_64_copy = []
    for r_x86_64 in rep_x86_64:
        if r_x86_64 not in rep_ppc64le:
            r_x86_64_copy.append(r_x86_64['pulp_href'])
    #package transfer
    if len(r_x86_64_copy) > 0:
        copy = await client.modify_repository(str_ppc64le, r_x86_64_copy)

async def main():
    pulp_host = 'http://127.0.0.1:8081'
    pulp_user = 'admin'
    pulp_password = 'admin'
    client = PulpClient(pulp_host, pulp_user, pulp_password)
    name = 'almalinux-8-powertools-x86_64'
    await copy_rep(client, name)

if __name__ == '__main__':
    asyncio.run(main())
