# Connect Apps Plugin

A Claude Code plugin that connects Claude to popular productivity and development apps via MCP (Model Context Protocol).

## Apps Included

| App | MCP Server Package | Auth Method |
|---|---|---|
| GitHub | `@modelcontextprotocol/server-github` | Personal Access Token |
| Gmail | `@gptscript-ai/gmail-mcp` | OAuth2 (Client ID/Secret/Refresh Token) |
| Google Calendar | `@modelcontextprotocol/server-google-calendar` | OAuth2 (Client ID/Secret/Refresh Token) |
| Google Drive | `@modelcontextprotocol/server-gdrive` | OAuth2 (Client ID/Secret/Refresh Token) |
| Jotform | `@jotform/mcp-server` | API Key |
| Miro | `@mirohq/mcp-server` | Access Token |

## Usage

```bash
claude --plugin-dir ./connect-apps-plugin
```

## Setup

### 1. GitHub

Create a [Personal Access Token](https://github.com/settings/tokens) with the scopes you need (e.g. `repo`, `read:org`).

```bash
export GITHUB_PERSONAL_ACCESS_TOKEN=ghp_...
```

### 2. Google (Gmail, Calendar, Drive)

These three services share the same OAuth2 credentials. Create a project in [Google Cloud Console](https://console.cloud.google.com/), enable the Gmail, Calendar, and Drive APIs, and generate OAuth2 credentials.

```bash
export GOOGLE_CLIENT_ID=...
export GOOGLE_CLIENT_SECRET=...
export GOOGLE_REFRESH_TOKEN=...
export GMAIL_CLIENT_ID=...
export GMAIL_CLIENT_SECRET=...
export GMAIL_REFRESH_TOKEN=...
```

### 3. Jotform

Grab your API key from [Jotform Account Settings](https://www.jotform.com/myaccount/api).

```bash
export JOTFORM_API_KEY=...
```

### 4. Miro

Generate an access token in [Miro Developer Portal](https://developers.miro.com/).

```bash
export MIRO_ACCESS_TOKEN=...
```

## Selective Loading

To load only specific integrations, comment out or remove the unwanted entries from `.mcp.json` before starting your session.

## Reloading

After editing `.mcp.json`, run `/reload-plugins` inside your Claude Code session to pick up the changes without restarting.
