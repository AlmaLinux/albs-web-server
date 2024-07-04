import typing
from urllib.parse import urljoin

from albs_github.graphql.client import IntegrationsGHGraphQLClient

from alws.config import settings
from alws.constants import ErrataPackagesType, GitHubIssueStatus


async def get_github_client() -> IntegrationsGHGraphQLClient:
    github_client = None
    github_token = settings.github_token
    if not github_token:
        app_id = settings.github_app_id
        pem = settings.path_to_github_app_pem
        installation_id = settings.github_installation_id
        if not all([
            app_id,
            pem,
            installation_id,
        ]):
            raise ValueError(
                'Config for GitHub integration is incomplete, '
                'please check the settings'
            )
        github_token = await IntegrationsGHGraphQLClient.generate_token_for_gh_app(
            gh_app_id=app_id,
            path_to_gh_app_pem=pem,
            installation_id=installation_id,
        )
    if not github_token:
        raise Exception("Can not get Github token")

    github_client = IntegrationsGHGraphQLClient(
        github_token,
        settings.github_organization_name,
        settings.github_project_number,
        settings.github_default_repository_name,
    )
    await github_client.initialize()
    return github_client


async def find_issues_by_repo_name(
    github_client: IntegrationsGHGraphQLClient,
    repo_names: list,
) -> typing.List[dict]:
    issue_ids = []
    for name in repo_names:
        query = f"conflict for {name} in:title"
        issue_ids.extend(await get_github_issue_content_ids(github_client, query))
    issue_ids = set(issue_ids)
    project_issues = await github_client.get_project_content_issues()
    filtered_issues = []
    valid_statuses = [
        GitHubIssueStatus.TODO.value,
        GitHubIssueStatus.DEVELOPMENT.value,
    ]
    for issue_id in list(issue_ids):
        project_issue = project_issues[issue_id]
        if project_issue.fields["Status"]["value"] in valid_statuses:
            filtered_issues.append(project_issue.model_dump())
    return filtered_issues


async def find_issues_by_record_id(
    github_client: IntegrationsGHGraphQLClient,
    record_ids: typing.List[str],
) -> typing.List[dict]:
    issue_ids = []
    for record_id in record_ids:
        query = f"{record_id} in:title"
        issue_ids.extend(await get_github_issue_content_ids(github_client, query))
    project_issues = await github_client.get_project_content_issues()
    issues = []
    for issue_id in list(issue_ids):
        project_issue = project_issues[issue_id]
        issues.append(project_issue.model_dump())
    return issues


async def find_issues_by_build_id(
    github_client: IntegrationsGHGraphQLClient,
    build_ids: typing.List[str],
) -> typing.List[dict]:
    project_issues = await github_client.get_project_issues()
    issues = []
    for project_issue_id in project_issues:
        project_issue = project_issues[project_issue_id]
        build_id = project_issue.fields.get("Build URL", {}).get("value")
        if not build_id:
            continue
        build_id = build_id.split('/')[-1]
        if build_id in build_ids:
            issues.append(project_issue.model_dump())
    return issues


async def set_build_id_to_issues(
    github_client: IntegrationsGHGraphQLClient,
    issues: list,
    build_id: str,
):
    url = urljoin(settings.frontend_baseurl, f"build/{build_id}")
    for issue in issues:
        issue_id = issue["id"]
        if "Build URL" in issue["fields"]:
            continue

        await github_client.set_text_field(
            issue_id=issue_id,
            field_name="Build URL",
            field_value=url,
        )
        comment = f"Build: {build_id}"
        await github_client.create_comment(item_id=issue_id, body=comment)


async def find_issues(
    github_client: IntegrationsGHGraphQLClient,
    record_ids: typing.Optional[typing.List[str]] = None,
    build_ids: typing.Optional[typing.List[str]] = None,
):
    issues = []
    if record_ids:
        issues.extend(
            await find_issues_by_record_id(
                github_client,
                record_ids,
            )
        )
    if build_ids:
        issues.extend(
            await find_issues_by_build_id(
                github_client=github_client,
                build_ids=build_ids,
            )
        )
    return issues


async def move_issue_to_testing(
    build_id: str,
    record_ids: typing.List[str],
):
    github_client = await get_github_client()
    issues = await find_issues(
        github_client=github_client,
        record_ids=record_ids,
        build_ids=[build_id],
    )
    issues = await filter_issues(
        issues=issues,
        valid_statuses=[
            GitHubIssueStatus.TODO.value,
            GitHubIssueStatus.DEVELOPMENT.value,
            GitHubIssueStatus.BUILDING.value,
        ],
    )
    await set_build_id_to_issues(
        github_client=github_client,
        issues=issues,
        build_id=build_id,
    )
    await move_issues(
        github_client=github_client,
        issues=issues,
        status=GitHubIssueStatus.TESTING.value,
    )


async def filter_issues(
    issues: list,
    valid_statuses: typing.Optional[list] = None,
    platform: typing.Optional[str] = None,
):
    filtered = []
    for issue in issues:
        condition = []
        if valid_statuses:
            condition.append(issue["fields"]["Status"]["value"] in valid_statuses)
        if platform:
            condition.append(issue["fields"]["Platform"]["value"] == platform)
        if all(condition):
            filtered.append(issue)
    return filtered


async def move_issues(
    github_client: IntegrationsGHGraphQLClient,
    issues: list,
    status: str,
):
    for issue in issues:
        issue_id = issue["id"]
        await github_client.set_issue_status(
            issue_id=issue_id,
            status=status,
        )


async def close_issues(
    record_ids: typing.Optional[typing.List[str]] = None,
    build_ids: typing.Optional[typing.List[str]] = None,
):
    issues = []
    github_client = await get_github_client()
    issues = await find_issues(
        github_client=github_client,
        record_ids=record_ids,
        build_ids=build_ids,
    )
    for issue in issues:
        issue_id = issue["content"]["id"]
        await github_client.close_issue(
            issue_id=issue_id,
        )
        comment = f"{record_ids} is released"
        await github_client.create_comment(item_id=issue_id, body=comment)


async def get_github_issue_content_ids(
    github_client: IntegrationsGHGraphQLClient,
    query: str,
) -> typing.List[str]:
    issues = []
    response = await github_client.serach_issues(query)
    edges = response.get("data", {}).get("search", {}).get("edges", [])
    for edge in edges:
        issue = edge["node"]
        issues.append(issue["id"])
    return issues


async def create_github_issue(
    client: IntegrationsGHGraphQLClient,
    title: str,
    description: str,
    advisory_id: str,
    original_id: str,
    platform_name: str,
    severity: str,
    packages: list,
    platform_id: str,
    find_packages_types: typing.Optional[list] = None,
):
    packages_section = "\n".join(
        (f"{p.name}-{p.version}-{p.release}.{p.arch}" for p in packages)
    )
    main_package = packages[0]
    name = f"{main_package.name}-{main_package.version}-{main_package.release}"
    issue_title = f'Release {name} {advisory_id}'
    issue_body = (
        f'{title}\nSeverity: {severity}\n'
        f'Description\n{description}\n\n'
        f'Affected packages:\n{packages_section}'
    )
    issue_id, project_item_id = await client.create_issue(issue_title, issue_body)
    await client.set_issue_platform(project_item_id, platform_name)
    errata_url = urljoin(
        settings.frontend_baseurl,
        f"/errata?id={advisory_id}&platform_id={platform_id}",
    )
    await client.set_text_field(
        issue_id=project_item_id,
        field_name="Errata URL",
        field_value=errata_url,
    )
    await client.set_text_field(project_item_id, 'Upstream ID', original_id)
    await client.set_text_field(project_item_id, 'AlmaLinux ID', advisory_id)
    comment = f"Errata created in ALBS: {errata_url}"
    await client.create_comment(item_id=issue_id, body=comment)
    if not find_packages_types:
        comment = "Can not find packages in any repos"
        await client.create_comment(item_id=issue_id, body=comment)
        return

    comments = set()
    build_ids = set()
    for pkg in find_packages_types:
        if pkg["type"] == ErrataPackagesType.BUILD:
            for build_id in pkg["build_ids"]:
                build_ids.add(build_id)
        else:
            comments.add("Find packages in prod repos")
    for build_id in build_ids:
        url = urljoin(settings.frontend_baseurl, f"build/{build_id}")
        await client.set_text_field(
            issue_id=project_item_id,
            field_name="Build URL",
            field_value=url,
        )
        comments.add(f"Find packages in Build: {url}")
    for comment in comments:
        await client.create_comment(item_id=issue_id, body=comment)
    await client.set_issue_status(
        issue_id=issue_id,
        status=GitHubIssueStatus.TESTING.value,
    )
