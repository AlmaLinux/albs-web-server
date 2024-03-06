import typing
from urllib.parse import urljoin

from albs_github.graphql.client import IntegrationsGHGraphQLClient

from alws.config import settings

__all__ = [
    'get_github_client',
    'find_issues_by_record_id',
    'find_issues_by_repo_name',
    'move_issues',
    'create_github_issue',
    'set_build_id_to_issues',
]


async def get_github_client() -> IntegrationsGHGraphQLClient:
    github_client = None
    github_token = settings.github_token
    if not github_token:
        raise ValueError(
            'Config for GitHub integration is incomplete, '
            'please check the settings'
        )
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
        query = f"{name} in:title,body"
        issue_ids.extend(
            await get_github_issue_content_ids(github_client, query)
        )
    issue_ids = set(issue_ids)
    project_issues = await github_client.get_project_content_issues()
    filtered_issues = []
    valid_statuses = ["Todo", "In Development"]
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
        issue_ids.extend(
            await get_github_issue_content_ids(github_client, query)
        )
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
    for issue in issues:
        issue_id = issue["id"]
        url = urljoin(settings.frontend_baseurl, f"build/{build_id}")
        await github_client.set_text_field(
            issue_id=issue_id,
            field_name="Build URL",
            field_value=url,
        )


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
):
    packages_section = "\n".join(
        (
            f"{p['name']}-{p['version']}-{p['release']}.{p['arch']}"
            for p in packages
        )
    )
    main_package = packages[0]
    name = f"{main_package['name']}-{main_package['version']}-{main_package['release']}"
    issue_title = f'Release {name} {advisory_id}'
    issue_body = (
        f'{title}\nSeverity: {severity}\n'
        f'Description\n{description}\n\n'
        f'Affected packages:\n{packages_section}'
    )
    issue_id, project_item_id = await client.create_issue(
        issue_title, issue_body
    )
    await client.set_issue_platform(project_item_id, platform_name)
    await client.set_text_field(project_item_id, 'Upstream ID', original_id)
    await client.set_text_field(project_item_id, 'AlmaLinux ID', advisory_id)
