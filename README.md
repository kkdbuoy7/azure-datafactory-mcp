# ADF MCP Server

Connect GitHub Copilot directly to Azure Data Factory. Manage pipelines, datasets, linked services, triggers, and more — all from Copilot Chat in VS Code.

---

## What You Can Do

- List, trigger, monitor, and cancel pipeline runs
- Debug failed runs down to the activity level
- Create and update pipelines, datasets, linked services, and triggers
- Start/stop triggers
- Export and deploy ARM templates (TST → PRD promotion)

> **Access control:** Every item you create must include your initials as a name segment (e.g. `ST_MyPipeline`). You can only create or update items with your own initials — you cannot overwrite a teammate's resources. Delete operations are disabled for safety.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.9+ | [python.org/downloads](https://www.python.org/downloads/) |
| VS Code | [code.visualstudio.com](https://code.visualstudio.com/) |
| GitHub Copilot extension | Install from VS Code Extensions marketplace |
| Azure access | Your Entra ID account needs **Data Factory Contributor** role on the factory (ask your Azure admin) |

---

## Setup (One-Time)

### Option A — Automated (recommended)

Open PowerShell in the project folder and run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\setup.ps1
```

The script will:
- Create a Python virtual environment
- Install all dependencies
- Create your `.env` file from the template and prompt you to fill it in

### Option B — Manual

```powershell
# 1. Create virtual environment
python -m venv .venv

# 2. Activate it
.\.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create your .env file
Copy-Item .env.example .env
```

Then open `.env` and fill in the three values:

```
AZURE_SUBSCRIPTION_ID=<your-subscription-id>
AZURE_RESOURCE_GROUP=<your-resource-group>
AZURE_FACTORY_NAME=<your-factory-name>
```

> Ask your team lead for these values — they are the same for everyone on the team.

---

## Connect to VS Code

1. Open the project folder in VS Code:
   ```
   code .
   ```
2. VS Code will automatically detect `.vscode/mcp.json` and register the MCP server — no extra configuration needed.

---

## First Use

1. Open **Copilot Chat** in VS Code (`Ctrl+Alt+I`)
2. Select **Agent mode** (the `@` icon or agent selector)
3. Type any ADF-related request, for example:
   - *"List all pipelines in ADF"*
   - *"Show me all failed runs in the last 24 hours"*
   - *"Build me an end-to-end pipeline that copies data from blob to SQL"*
4. **A browser window will open** the first time — sign in with your Microsoft/Entra ID account.
5. After sign-in the token is cached for the session. Subsequent calls are silent.

---

## Naming Convention

All resources you create must follow the pattern:

```
<YOUR_INITIALS>_<ResourceName>
```

Examples:
| Your Name | Initials | Valid Name |
|---|---|---|
| Sri Thamm | ST | `ST_LoadCustomers` |
| John Doe | JD | `JD_BlobToSQL` |
| Ana Rivera | AR | `AR_DailyTrigger` |

Your initials are derived automatically from your Entra ID display name. If a name doesn't include your initials as a segment, the server will block the operation and tell you what to use.

---

## How Copilot Behaves for Pipeline Builds

When you ask Copilot to **build an end-to-end pipeline**, it will:

1. Write out a full plan (activities, dependencies, datasets, triggers) before touching anything
2. Ask *"Does this plan look correct? Should I go ahead?"*
3. Check for reusable existing datasets, linked services, and triggers before creating new ones
4. Build in dependency order: linked services → datasets → pipeline → trigger

---

## Project Structure

```
adf-mcp/
├── server.py                    # MCP server — all ADF tools live here
├── requirements.txt             # Python dependencies
├── setup.ps1                    # One-click setup script
├── .env.example                 # Config template (commit this)
├── .env                         # Your local config (git-ignored, never commit)
├── .vscode/
│   └── mcp.json                 # VS Code MCP server registration (auto-detected)
├── .github/
│   └── copilot-instructions.md  # Copilot workflow rules for ADF
├── README.md                    # This file
└── ADF_MCP_Capabilities.md      # Full tool reference
```

---

## Full Tool Reference

See [ADF_MCP_Capabilities.md](ADF_MCP_Capabilities.md) for a complete list of all available tools and use-case examples.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| *"MCP server not found"* | Make sure `.venv` exists and `pip install -r requirements.txt` has been run |
| *"Access denied — initials not found"* | Rename your resource to include your initials as a segment, e.g. `ST_MyPipeline` |
| *"No browser opened"* | Check that a default browser is configured on your machine |
| *"Token/auth error"* | Close VS Code, reopen, and sign in again on first tool call |
| *"Factory not found"* | Double-check the three values in your `.env` file |
