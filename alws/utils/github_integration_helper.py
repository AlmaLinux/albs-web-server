import typing

from albs_github.graphql.client import IntegrationsGHGraphQLClient

from alws.config import settings

__all__ = [
    'get_github_client',
    'find_issues_by_record_id',
    'move_issues_to_testing_section'
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


async def find_issues_by_record_id(
    github_client: IntegrationsGHGraphQLClient,
    record_ids: str,
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


async def move_issues_to_testing_section(
    github_client: IntegrationsGHGraphQLClient,
    issues: list,
):
    for issue in issues:
        issue_id = issue["id"]
        await github_client.set_issue_status(
            issue_id=issue_id, status="Testing"
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
