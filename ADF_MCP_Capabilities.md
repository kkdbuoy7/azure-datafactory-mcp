# ADF MCP Server — Capabilities Reference

## Overview

The `adf-tst` MCP server exposes Azure Data Factory (ADF) management operations as tools that can be invoked directly from GitHub Copilot Chat. It connects to a single ADF factory (configured via environment variables) and is launched as a local `stdio` process.

**Server name:** `adf-tst`  
**Transport:** stdio  
**Entry point:** `server.py`  
**Auth:** Azure Entra ID — `InteractiveBrowserCredential` (browser sign-in on first use, no service principal required)

---

## Configuration (Environment Variables)

Create a `.env` file in the project root (copy from `.env.example`):

| Variable | Description |
|---|---|
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID |
| `AZURE_RESOURCE_GROUP` | Resource group containing the factory |
| `AZURE_FACTORY_NAME` | ADF factory name |

> No service principal credentials are needed. Each user authenticates with their own Entra ID account via an interactive browser sign-in on first use.

---

## Access Control & Naming Rules

All **create / update** operations enforce an ownership rule:

- The resource name **must contain the user's initials as a distinct segment** (e.g. `ST_MyPipeline`, `Pipeline_ST`, `ST_Dataset_Blob`).
- Initials are derived automatically from the signed-in user's Entra ID display name (e.g. "Sri Thamm" → `ST`).
- Users can only create or update items that carry their own initials — they cannot overwrite another team member's resources.
- **Delete operations have been disabled** for all resource types (pipelines, datasets, linked services, triggers) to protect shared factory resources.

---

## Pipeline Building Workflow (Copilot Behaviour)

When asked to build an end-to-end pipeline, Copilot will:

1. **Plan first** — produce a written plan (activities, dependencies, parameters, datasets, triggers) before calling any tool.
2. **Wait for your confirmation** before creating anything.
3. **Reuse existing resources** — checks `list_linked_services`, `list_datasets`, `list_triggers`, and existing pipeline definitions for reusable items before creating new ones.
4. **Build in dependency order** — linked services → datasets → pipeline → trigger.

---

## Tool Capabilities

### Pipeline Operations

| Tool | Description |
|---|---|
| `list_pipelines` | List all pipelines in the factory |
| `trigger_pipeline` | Trigger a pipeline run (with optional parameters); returns `run_id` |
| `get_run_status` | Get current status of a run by `run_id` (Queued / InProgress / Succeeded / Failed / Cancelled) |
| `cancel_pipeline_run` | Cancel an in-progress pipeline run |
| `get_failed_runs` | List all failed runs in the last N hours (default: 24h) — useful for health checks |
| `get_recent_runs` | Get all runs (any status) for a specific pipeline over a time window |
| `get_pipeline_definition` | Retrieve the full JSON definition of a pipeline |
| `create_or_update_pipeline` | Create or upsert a pipeline *(name must include your initials)* |

---

### Trigger Operations

| Tool | Description |
|---|---|
| `list_triggers` | List all triggers with type and runtime state (Started / Stopped) |
| `start_trigger` | Start a stopped trigger |
| `stop_trigger` | Stop a running trigger |
| `get_trigger_definition` | Get the full JSON definition of a trigger |
| `create_or_update_schedule_trigger` | Create/update a schedule trigger attached to a pipeline *(name must include your initials)* |
| `create_or_update_blob_event_trigger` | Create/update a blob event trigger on blob created/deleted events *(name must include your initials)* |

---

### Dataset Operations

| Tool | Description |
|---|---|
| `list_datasets` | List all datasets in the factory |
| `get_dataset_definition` | Get the full JSON definition of a dataset |
| `create_or_update_dataset` | Create or upsert a dataset *(name must include your initials)* |

---

### Linked Service Operations

| Tool | Description |
|---|---|
| `list_linked_services` | List all linked services in the factory |
| `get_linked_service_definition` | Get the full JSON definition of a linked service |
| `create_or_update_linked_service` | Create or upsert a linked service *(name must include your initials)* |

---

### Integration Runtime / SHIR Operations

| Tool | Description |
|---|---|
| `list_integration_runtimes` | List all Integration Runtimes (including Self-Hosted IRs) with their current state |
| `list_pipelines_using_shir` | Find all pipelines that reference a specific SHIR — useful before maintenance windows |

---

### Activity-Level Debugging

| Tool | Description |
|---|---|
| `get_activity_runs` | Get per-activity run details for a pipeline run (name, type, status, duration, input, output, error) — essential for pinpointing failures |

---

### ARM Template / Deployment Operations

| Tool | Description |
|---|---|
| `deploy_arm_template` | Deploy an ARM template to the resource group (Incremental mode) |
| `get_deployment_status` | Check status of an ARM deployment by name, including per-resource operation details |
| `export_factory_arm_template` | Export the entire ADF factory as an ARM template — useful for backup or promoting TST → PRD |

---

## Capability Summary by Use Case

| Use Case | Tools to Use |
|---|---|
| Morning health check | `get_failed_runs` |
| Trigger a pipeline manually | `trigger_pipeline` → `get_run_status` |
| Debug a failed run | `get_failed_runs` → `get_activity_runs` |
| Manage schedules | `list_triggers`, `start_trigger`, `stop_trigger`, `create_or_update_schedule_trigger` |
| React to file arrivals | `create_or_update_blob_event_trigger` |
| SHIR maintenance planning | `list_integration_runtimes`, `list_pipelines_using_shir` |
| Deploy / promote to another env | `export_factory_arm_template` → `deploy_arm_template` |
| Inspect or clone a pipeline | `get_pipeline_definition` → `create_or_update_pipeline` |

---

## Team Setup Guide

### Prerequisites
- Python 3.9+
- VS Code with the **GitHub Copilot** extension
- Access to the Azure subscription/resource group (your Entra ID account must have at least **Data Factory Contributor** role on the factory)

### Steps

1. **Clone the repository**
   ```
   git clone <repo-url>
   cd adf-mcp
   ```

2. **Create a virtual environment and install dependencies**
   ```
   python -m venv .venv
   .venv\Scripts\activate        # Windows
   pip install -r requirements.txt
   ```

3. **Create your `.env` file** (copy from `.env.example`)
   ```
   cp .env.example .env
   ```
   Fill in `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP`, and `AZURE_FACTORY_NAME`.

4. **Open the folder in VS Code**
   The `.vscode/mcp.json` is already configured — VS Code will automatically start the MCP server.

5. **First use — sign in**
   When you invoke any Copilot tool for the first time, a browser window will open asking you to sign in with your Microsoft/Entra ID account. After sign-in the token is cached for the session.

### File Structure
```
adf-mcp/
├── server.py                  # MCP server — all ADF tools
├── requirements.txt           # Python dependencies
├── .env.example               # Template for environment config
├── .env                       # Your local config (git-ignored)
├── .vscode/
│   └── mcp.json               # VS Code MCP server registration
├── .github/
│   └── copilot-instructions.md  # Copilot behaviour rules for ADF workflows
└── ADF_MCP_Capabilities.md    # This file
```
