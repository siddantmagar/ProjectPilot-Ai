import httpx

from app.integrations.jira.client import _auth_header, _load_config


base_url, email, token, project_key = _load_config()
response = httpx.get(
    f"{base_url}/rest/api/3/project/{project_key}/statuses",
    headers=_auth_header(email, token),
    timeout=10,
)
response.raise_for_status()
for issue_type in response.json():
    print(f"\nIssue type: {issue_type['name']}")
    for status in issue_type["statuses"]:
        print(
            f"  - {status['name']} "
            f"(id={status['id']}, category={status['statusCategory']['name']})"
        )
