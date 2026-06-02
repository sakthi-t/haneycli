"""Create v0.1.1 release on GitHub."""
import requests
import os
import re

# Try to get token from MCP config or env
token = os.environ.get("GITHUB_TOKEN")

# Fallback: read from .env
if not token:
    try:
        with open(".env") as f:
            content = f.read()
        match = re.search(r'GITHUB_TOKEN=(\S+)', content)
        if match:
            token = match.group(1)
    except FileNotFoundError:
        pass

# Fallback: read from haney config
if not token:
    try:
        import json
        with open(".haney/config.json") as f:
            config = json.load(f)
        # Check for MCP github token
        token = config.get("mcp", {}).get("servers", {}).get("github", {}).get("token")
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        pass

if not token:
    print("❌ No GitHub token found. Set GITHUB_TOKEN env var or add to .env")
    exit(1)

resp = requests.post(
    "https://api.github.com/repos/sakthi-t/haneycli/releases",
    headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    },
    json={
        "tag_name": "v0.1.1",
        "target_commitish": "66098cc",
        "name": "v0.1.1 - GitHub MCP Implemented",
        "body": (
            "## Haney v0.1.1\n\n"
            "###  New Features\n"
            "- **GitHub MCP Integration** - Full GitHub Model Context Protocol support\n"
            "  - Connect/authenticate with GitHub via OAuth device flow\n"
            "  - Repository management, issue tracking, PR review, file operations\n"
            "  - Search across repositories, code, issues, and users\n"
            "  - All MCP tools integrate with Haney's existing approval/permission system\n\n"
            "###  Fixes\n"
            "- Cleaned up `.gitignore` redundancies (`sessions/` and `trash/` scoped to `.haney/`)\n"
            "- Removed duplicate `.haney/`, `dist/`, `build/`, `.egg-info/` entries\n\n"
            "###  MCP Commands\n"
            "```bash\n"
            "/mcp login github      # GitHub OAuth device flow\n"
            "/mcp connect github    # Start the GitHub MCP server\n"
            "/mcp status            # View connected servers and tools\n"
            "/mcp servers           # List available MCP servers\n"
            "```"
        ),
        "draft": False,
        "prerelease": False,
    },
)

if resp.status_code in (200, 201):
    data = resp.json()
    print(f"✅ Release created: {data['html_url']}")
    print(f"   Tag: {data['tag_name']}")
else:
    print(f"❌ Failed: {resp.status_code}")
    print(resp.text[:500])
