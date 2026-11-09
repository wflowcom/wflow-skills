# wflow skills

Agent skills for [wflow.com](https://www.wflow.com), the document approval platform. Each skill teaches your AI
agent a multi-step wflow task: which calls to make, in what order, and where to stop and ask you. The skills work
through the wflow MCP server, so connect it as described below before you use them.

## Skills

- **approval-paths** — Design, review, export, bulk-edit, create and copy approval paths (approval templates) in wflow.com through the wflow MCP.
- **audit-trail** — Generate an audit-trail PDF (event history) for wflow.com documents in the "Sent to ERP" (SentToERP) state through the wflow MCP and attach it to each document as a regular attachment.
- **issued-invoices-import** — Import issued (outgoing) invoices that were created in another system – invoicing tool, e-shop, ERP, a hand-kept Excel – from any xls / xlsx / csv into wflow.com through the wflow MCP, optionally with their PDFs.
- **user-management** — Manage users and roles in wflow.com via the wflow MCP: user onboarding (manually or by a template user, also across multiple organizations), creating / editing / auditing a role, delegation (starting and ending a substitution), offboarding (removing a user, optionally with a successor) and a user overview in Excel.

## Connect the wflow MCP

The skills call wflow through its MCP server at `https://mcp.wflow.com/mcp`. When your client first connects, it
opens the wflow sign-in page and you sign in with your wflow account (OAuth). Every call then runs as you and sees
only what your wflow rights allow. No credentials are stored in this repository or in the plugin.

## Install

### Claude.ai and Claude Desktop

1. Open **Customize → Plugins → Discover**, find **wflow** and select **Install**.
2. Open **Connectors** and connect **wflow**, then sign in with your wflow account.

### Claude Code

Add the marketplace, install the plugin, then connect the MCP server:

```text
/plugin marketplace add wflowcom/wflow-skills
/plugin install wflow@wflow-skills
/mcp
```

In `/mcp`, select **wflow** and sign in with your wflow account. To get new skill versions automatically, run
`/plugin`, open the **Marketplaces** tab, select **wflow-skills** and choose **Enable auto-update**.

Administrators can roll the plugin out to the whole organization with auto-update on by adding this to Claude
Code's managed settings:

```json
{
  "extraKnownMarketplaces": {
    "wflow-skills": {
      "source": {
        "source": "github",
        "repo": "wflowcom/wflow-skills"
      },
      "autoUpdate": true
    }
  },
  "enabledPlugins": {
    "wflow@wflow-skills": true
  }
}
```

### Cursor

Open **Customize**, choose **From GitHub Repository** and enter `wflowcom/wflow-skills`. The plugin brings the wflow
MCP server with it; sign in with your wflow account when Cursor asks.

On a Cursor Teams plan, an administrator can import this repository into the team marketplace instead, so everyone
on the team can install the plugin from **Customize**.

### ChatGPT

Once wflow is listed in the ChatGPT plugin directory:

1. Open **Plugins**, search for **wflow** and install it.
2. Connect it and sign in with your wflow account.
3. Start a new chat and type `@wflow`.

On a ChatGPT Business, Enterprise or Edu workspace, an administrator can import this repository instead: open
**Admin → Plugins → Add → Import marketplace** and set the source to `https://github.com/wflowcom/wflow-skills`.
Plugins imported this way may be available only in the ChatGPT desktop app.

To connect only the wflow MCP server (Business, Enterprise and Edu), open **Plugins** on chatgpt.com, select
**+ → Add custom MCP server**, enter `https://mcp.wflow.com/mcp`, choose **OAuth** and sign in with your wflow
account.

### Codex CLI

Add the marketplace and install the plugin, then sign in with your wflow account when Codex asks:

```bash
codex plugin marketplace add wflowcom/wflow-skills
codex plugin add wflow@wflow-skills
```

To connect only the wflow MCP server:

```bash
codex mcp add wflow --url https://mcp.wflow.com/mcp
codex mcp login wflow
```

### LibreChat

Add the skills and the MCP server to `librechat.yaml`:

```yaml
skillSync:
  github:
    sources:
      - id: wflow-skills
        owner: wflowcom
        repo: wflow-skills
        ref: main
        paths:
          - skills

mcpServers:
  wflow:
    type: streamable-http
    url: https://mcp.wflow.com/mcp
```

### Other agents

Install the skills with the `skills` CLI:

```bash
npx skills add wflowcom/wflow-skills
```

Then add `https://mcp.wflow.com/mcp` as a remote MCP server in your agent's settings and sign in with your wflow
account.

## Privacy Policy

See the [wflow Privacy Policy](https://www.wflow.com/en/privacy-policy).

## License

Licensed under the Apache License 2.0. See [LICENSE](LICENSE).

This repository is generated; report issues at <https://support.wflow.com/en/>.
