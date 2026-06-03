from mcp.server.fastmcp import FastMCP
from azure.identity import InteractiveBrowserCredential
from azure.mgmt.datafactory import DataFactoryManagementClient
from azure.mgmt.datafactory.models import (
    RunFilterParameters,
    PipelineResource,
    DatasetResource,
    LinkedServiceResource,
    ScheduleTrigger,
    ScheduleTriggerRecurrence,
    TriggerPipelineReference,
    TriggerResource,
    PipelineReference,
    BlobEventsTrigger,
)
from azure.mgmt.resource import ResourceManagementClient
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from typing import Optional
import os
import json
import base64
import re

load_dotenv()

# ── Credentials ────────────────────────────────────────────────────────────────
# Uses interactive browser sign-in (Entra ID). A browser window opens on
# first use; the token is then cached for the session.
SUBSCRIPTION_ID = os.getenv("AZURE_SUBSCRIPTION_ID")
RESOURCE_GROUP  = os.getenv("AZURE_RESOURCE_GROUP")
FACTORY_NAME    = os.getenv("AZURE_FACTORY_NAME")

credential     = InteractiveBrowserCredential()
adf_client     = DataFactoryManagementClient(credential, SUBSCRIPTION_ID)
arm_client     = ResourceManagementClient(credential, SUBSCRIPTION_ID)

mcp = FastMCP("ADF-TST")

# ── Helper ─────────────────────────────────────────────────────────────────────
def _rg(): return RESOURCE_GROUP
def _fn(): return FACTORY_NAME


def _get_user_initials() -> str:
    """
    Decode the current user's Azure access token and derive initials from their
    display name or UPN claim.
    e.g. "John Doe" → "JD",  "john.doe@company.com" → "JD"
    """
    token = credential.get_token("https://management.azure.com/.default")
    payload_b64 = token.token.split(".")[1]
    # JWT base64 may not be padded — fix that
    payload_b64 += "=" * (-len(payload_b64) % 4)
    payload = json.loads(base64.b64decode(payload_b64))

    # Prefer display name, fall back to UPN / preferred_username
    raw = (
        payload.get("name")
        or payload.get("upn", "").split("@")[0]
        or payload.get("preferred_username", "").split("@")[0]
    )
    # Split on spaces, dots, underscores, hyphens and take first letter of each part
    parts = re.split(r"[\s._\-]+", raw)
    initials = "".join(p[0].upper() for p in parts if p)
    return initials


def _assert_ownership(item_name: str) -> None:
    """
    Raise ValueError if item_name does not contain the current user's initials
    as a whole segment (split by _, -, or whitespace).
    e.g. initials "ST" matches "ST_Pipeline" or "Pipeline_ST" but NOT "WrongInitials_Test"
    even though 'test' contains the letters s and t.
    """
    initials = _get_user_initials()
    segments = re.split(r"[_\-\s]+", item_name)
    if not any(seg.upper() == initials.upper() for seg in segments):
        raise ValueError(
            f"Access denied: '{item_name}' does not contain your initials ('{initials}') "
            f"as a name segment. Name your item with '{initials}_' as a prefix, "
            f"e.g. '{initials}_MyPipeline'."
        )


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE TOOLS
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def list_pipelines() -> str:
    """List all pipelines in the ADF TST factory."""
    pipelines = list(adf_client.pipelines.list_by_factory(_rg(), _fn()))
    names = [p.name for p in pipelines]
    return json.dumps(names, indent=2)


@mcp.tool()
def trigger_pipeline(pipeline_name: str, parameters: Optional[dict] = None) -> str:
    """
    Trigger a pipeline run in ADF TST.
    Returns the run_id so you can track it.
    """
    run_response = adf_client.pipelines.create_run(
        _rg(), _fn(), pipeline_name,
        parameters=parameters or {}
    )
    return json.dumps({"run_id": run_response.run_id, "pipeline": pipeline_name})


@mcp.tool()
def get_run_status(run_id: str) -> str:
    """
    Get the current status of a pipeline run by run_id.
    Possible statuses: Queued, InProgress, Succeeded, Failed, Canceling, Cancelled.
    """
    run = adf_client.pipeline_runs.get(_rg(), _fn(), run_id)
    return json.dumps({
        "run_id":       run.run_id,
        "pipeline":     run.pipeline_name,
        "status":       run.status,
        "start":        str(run.run_start),
        "end":          str(run.run_end),
        "duration_ms":  run.duration_in_ms,
        "message":      run.message
    }, indent=2)


@mcp.tool()
def cancel_pipeline_run(run_id: str) -> str:
    """Cancel an in-progress pipeline run."""
    adf_client.pipeline_runs.cancel(_rg(), _fn(), run_id)
    return json.dumps({"status": "cancel_requested", "run_id": run_id})


@mcp.tool()
def get_failed_runs(hours_back: int = 24) -> str:
    """
    List all failed pipeline runs within the last N hours (default 24).
    Useful for morning health checks or incident triage.
    """
    now    = datetime.now(timezone.utc)
    since  = now - timedelta(hours=hours_back)

    filter_params = RunFilterParameters(
        last_updated_after=since,
        last_updated_before=now,
        filters=[{"operand": "Status", "operator": "Equals", "values": ["Failed"]}]
    )
    runs = adf_client.pipeline_runs.query_by_factory(_rg(), _fn(), filter_params)

    results = [
        {
            "run_id":   r.run_id,
            "pipeline": r.pipeline_name,
            "start":    str(r.run_start),
            "message":  r.message
        }
        for r in runs.value
    ]
    return json.dumps(results, indent=2)


@mcp.tool()
def get_recent_runs(pipeline_name: str, hours_back: int = 24) -> str:
    """
    Get recent runs (all statuses) for a specific pipeline.
    Good for checking if a pipeline has been running as expected.
    """
    now   = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours_back)

    filter_params = RunFilterParameters(
        last_updated_after=since,
        last_updated_before=now,
        filters=[{"operand": "PipelineName", "operator": "Equals", "values": [pipeline_name]}]
    )
    runs = adf_client.pipeline_runs.query_by_factory(_rg(), _fn(), filter_params)

    results = [
        {
            "run_id":      r.run_id,
            "status":      r.status,
            "start":       str(r.run_start),
            "duration_ms": r.duration_in_ms
        }
        for r in runs.value
    ]
    return json.dumps(results, indent=2)


# ══════════════════════════════════════════════════════════════════════════════
# TRIGGER TOOLS
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def list_triggers() -> str:
    """List all triggers with their current status (Started/Stopped)."""
    triggers = list(adf_client.triggers.list_by_factory(_rg(), _fn()))
    result = [
        {
            "name":       t.name,
            "type":       type(t.properties).__name__,
            "runtime_state": t.properties.runtime_state
        }
        for t in triggers
    ]
    return json.dumps(result, indent=2)


@mcp.tool()
def start_trigger(trigger_name: str) -> str:
    """Start a stopped trigger in ADF TST."""
    adf_client.triggers.begin_start(_rg(), _fn(), trigger_name).result()
    return json.dumps({"status": "started", "trigger": trigger_name})


@mcp.tool()
def stop_trigger(trigger_name: str) -> str:
    """Stop a running trigger in ADF TST."""
    adf_client.triggers.begin_stop(_rg(), _fn(), trigger_name).result()
    return json.dumps({"status": "stopped", "trigger": trigger_name})


# ══════════════════════════════════════════════════════════════════════════════
# SHIR / IR TOOLS
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def list_integration_runtimes() -> str:
    """List all Integration Runtimes (including SHIRs) and their status."""
    irs = list(adf_client.integration_runtimes.list_by_factory(_rg(), _fn()))
    result = []
    for ir in irs:
        status = adf_client.integration_runtimes.get_status(_rg(), _fn(), ir.name)
        result.append({
            "name":  ir.name,
            "type":  ir.properties.type,
            "state": status.properties.state if status.properties else "Unknown"
        })
    return json.dumps(result, indent=2)


@mcp.tool()
def list_pipelines_using_shir(shir_name: str) -> str:
    """
    Find all pipelines that reference a specific Self-Hosted Integration Runtime.
    Useful before maintenance — know what's affected.
    """
    pipelines = list(adf_client.pipelines.list_by_factory(_rg(), _fn()))
    affected = []

    for p in pipelines:
        pipeline_detail = adf_client.pipelines.get(_rg(), _fn(), p.name)
        pipeline_json   = pipeline_detail.serialize()
        if shir_name.lower() in json.dumps(pipeline_json).lower():
            affected.append(p.name)

    return json.dumps({"shir": shir_name, "pipelines": affected}, indent=2)


# ══════════════════════════════════════════════════════════════════════════════
# DATASET / LINKED SERVICE TOOLS
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def list_datasets() -> str:
    """List all datasets in the ADF TST factory."""
    datasets = list(adf_client.datasets.list_by_factory(_rg(), _fn()))
    return json.dumps([d.name for d in datasets], indent=2)


@mcp.tool()
def list_linked_services() -> str:
    """List all linked services in the ADF TST factory."""
    services = list(adf_client.linked_services.list_by_factory(_rg(), _fn()))
    return json.dumps([s.name for s in services], indent=2)


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE CREATE / UPDATE / DELETE
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def get_pipeline_definition(pipeline_name: str) -> str:
    """
    Get the full JSON definition of a pipeline.
    Returns the complete pipeline spec including all activities, dependencies,
    parameters, and variables — useful for inspection or cloning.
    """
    pipeline = adf_client.pipelines.get(_rg(), _fn(), pipeline_name)
    return json.dumps(pipeline.serialize(), indent=2)


@mcp.tool()
def create_or_update_pipeline(pipeline_name: str, pipeline_definition: dict) -> str:
    """
    Create or update a pipeline from a JSON definition dict.
    The pipeline_definition should follow the ADF pipeline resource schema:
    {
      "activities": [...],
      "parameters": {...},   # optional
      "variables":  {...},   # optional
      "description": "..."   # optional
    }
    If the pipeline_name already exists it will be overwritten (upsert).
    """
    try:
        _assert_ownership(pipeline_name)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    resource = PipelineResource(
        activities=pipeline_definition.get("activities", []),
        parameters=pipeline_definition.get("parameters"),
        variables=pipeline_definition.get("variables"),
        description=pipeline_definition.get("description"),
        additional_properties=pipeline_definition.get("additional_properties"),
    )
    result = adf_client.pipelines.create_or_update(_rg(), _fn(), pipeline_name, resource)
    return json.dumps({"status": "upserted", "pipeline": result.name}, indent=2)



# ══════════════════════════════════════════════════════════════════════════════
# DATASET CREATE / UPDATE / DELETE
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def get_dataset_definition(dataset_name: str) -> str:
    """Get the full JSON definition of a dataset."""
    dataset = adf_client.datasets.get(_rg(), _fn(), dataset_name)
    return json.dumps(dataset.serialize(), indent=2)


@mcp.tool()
def create_or_update_dataset(dataset_name: str, dataset_definition: dict) -> str:
    """
    Create or update a dataset from a JSON definition dict.
    The dataset_definition must include a 'type' key and 'typeProperties'.
    Example for Azure Blob CSV:
    {
      "type": "DelimitedText",
      "linkedServiceName": {"referenceName": "AzureBlobStorage1", "type": "LinkedServiceReference"},
      "typeProperties": {
        "location": {"type": "AzureBlobStorageLocation", "container": "mycontainer", "folderPath": "input"},
        "columnDelimiter": ",",
        "firstRowAsHeader": true
      }
    }
    """
    try:
        _assert_ownership(dataset_name)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    resource = DatasetResource(properties=dataset_definition)
    result = adf_client.datasets.create_or_update(_rg(), _fn(), dataset_name, resource)
    return json.dumps({"status": "upserted", "dataset": result.name}, indent=2)



# ══════════════════════════════════════════════════════════════════════════════
# LINKED SERVICE CREATE / UPDATE / DELETE
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def get_linked_service_definition(service_name: str) -> str:
    """Get the full JSON definition of a linked service."""
    svc = adf_client.linked_services.get(_rg(), _fn(), service_name)
    return json.dumps(svc.serialize(), indent=2)


@mcp.tool()
def create_or_update_linked_service(service_name: str, service_definition: dict) -> str:
    """
    Create or update a linked service from a JSON definition dict.
    The service_definition must include 'type' and 'typeProperties'.
    Example for Azure Blob Storage (Account Key):
    {
      "type": "AzureBlobStorage",
      "typeProperties": {
        "connectionString": "DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;EndpointSuffix=core.windows.net"
      }
    }
    Example for Azure SQL Database:
    {
      "type": "AzureSqlDatabase",
      "typeProperties": {
        "connectionString": "Server=tcp:myserver.database.windows.net;Database=mydb;User ID=user;Password=pass;"
      }
    }
    """
    try:
        _assert_ownership(service_name)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    resource = LinkedServiceResource(properties=service_definition)
    result = adf_client.linked_services.create_or_update(_rg(), _fn(), service_name, resource)
    return json.dumps({"status": "upserted", "linked_service": result.name}, indent=2)



# ══════════════════════════════════════════════════════════════════════════════
# TRIGGER CREATE / UPDATE / DELETE
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def get_trigger_definition(trigger_name: str) -> str:
    """Get the full JSON definition of a trigger."""
    trigger = adf_client.triggers.get(_rg(), _fn(), trigger_name)
    return json.dumps(trigger.serialize(), indent=2)


@mcp.tool()
def create_or_update_schedule_trigger(
    trigger_name: str,
    pipeline_name: str,
    frequency: str,
    interval: int,
    start_time: str,
    end_time: Optional[str] = None,
    pipeline_parameters: Optional[dict] = None,
    time_zone: str = "UTC",
) -> str:
    """
    Create or update a ScheduleTrigger and attach it to a pipeline.

    Args:
        trigger_name:        Name for the trigger.
        pipeline_name:       Pipeline to fire when triggered.
        frequency:           Recurrence unit — Minute | Hour | Day | Week | Month.
        interval:            How many units between fires (e.g. frequency=Hour, interval=4 → every 4 hours).
        start_time:          ISO-8601 UTC start time, e.g. "2026-06-01T00:00:00Z".
        end_time:            ISO-8601 UTC end time (optional, omit for indefinite).
        pipeline_parameters: Dict of parameters to pass to the pipeline on each run.
        time_zone:           Time zone string, default "UTC".
    """
    try:
        _assert_ownership(trigger_name)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    recurrence = ScheduleTriggerRecurrence(
        frequency=frequency,
        interval=interval,
        start_time=datetime.fromisoformat(start_time.replace("Z", "+00:00")),
        end_time=datetime.fromisoformat(end_time.replace("Z", "+00:00")) if end_time else None,
        time_zone=time_zone,
    )
    pipeline_ref = TriggerPipelineReference(
        pipeline_reference=PipelineReference(reference_name=pipeline_name, type="PipelineReference"),
        parameters=pipeline_parameters or {},
    )
    trigger_resource = TriggerResource(
        properties=ScheduleTrigger(
            recurrence=recurrence,
            pipelines=[pipeline_ref],
        )
    )
    result = adf_client.triggers.create_or_update(_rg(), _fn(), trigger_name, trigger_resource)
    return json.dumps({"status": "upserted", "trigger": result.name}, indent=2)


@mcp.tool()
def create_or_update_blob_event_trigger(
    trigger_name: str,
    pipeline_name: str,
    storage_account_resource_id: str,
    container_name: str,
    blob_path_begins_with: Optional[str] = None,
    blob_path_ends_with: Optional[str] = None,
    events: Optional[list] = None,
    pipeline_parameters: Optional[dict] = None,
) -> str:
    """
    Create or update a BlobEventsTrigger (fires when blobs are created/deleted).

    Args:
        trigger_name:                  Name for the trigger.
        pipeline_name:                 Pipeline to fire on the blob event.
        storage_account_resource_id:   Full ARM resource ID of the storage account.
        container_name:                Blob container to monitor.
        blob_path_begins_with:         Optional prefix filter e.g. "/mycontainer/blobs/input/".
        blob_path_ends_with:           Optional suffix filter e.g. ".csv".
        events:                        List of events to react to.
                                       Default: ["Microsoft.Storage.BlobCreated"].
        pipeline_parameters:           Dict of parameters to pass to the pipeline.
    """
    try:
        _assert_ownership(trigger_name)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    pipeline_ref = TriggerPipelineReference(
        pipeline_reference=PipelineReference(reference_name=pipeline_name, type="PipelineReference"),
        parameters=pipeline_parameters or {},
    )
    trigger_resource = TriggerResource(
        properties=BlobEventsTrigger(
            scope=storage_account_resource_id,
            events=events or ["Microsoft.Storage.BlobCreated"],
            blob_path_begins_with=blob_path_begins_with,
            blob_path_ends_with=blob_path_ends_with,
            pipelines=[pipeline_ref],
        )
    )
    result = adf_client.triggers.create_or_update(_rg(), _fn(), trigger_name, trigger_resource)
    return json.dumps({"status": "upserted", "trigger": result.name}, indent=2)



# ══════════════════════════════════════════════════════════════════════════════
# ACTIVITY-LEVEL RUN DETAILS
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def get_activity_runs(run_id: str, hours_back: int = 24) -> str:
    """
    Get activity-level run details for a specific pipeline run_id.
    Shows each activity's name, type, status, duration, input, output and error.
    Essential for debugging which step inside a pipeline failed.
    """
    now   = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours_back)

    filter_params = RunFilterParameters(
        last_updated_after=since,
        last_updated_before=now,
    )
    activities = adf_client.activity_runs.query_by_pipeline_run(
        _rg(), _fn(), run_id, filter_params
    )

    results = []
    for a in activities.value:
        results.append({
            "activity_name":      a.activity_name,
            "activity_type":      a.activity_type,
            "status":             a.status,
            "start":              str(a.activity_run_start),
            "end":                str(a.activity_run_end),
            "duration_ms":        a.duration_in_ms,
            "input":              a.input,
            "output":             a.output,
            "error":              a.error,
        })
    return json.dumps(results, indent=2)


# ══════════════════════════════════════════════════════════════════════════════
# ARM TEMPLATE DEPLOYMENT
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def deploy_arm_template(
    deployment_name: str,
    arm_template: dict,
    arm_parameters: Optional[dict] = None,
) -> str:
    """
    Deploy an ARM template to the current resource group.
    Use this to deploy ADF resources (pipelines, datasets, triggers, linked services)
    exported from ADF Studio or built manually.

    Args:
        deployment_name:  A unique name for this deployment (used to track it).
        arm_template:     The full ARM template as a dict (the contents of azuredeploy.json).
        arm_parameters:   Optional parameters dict in ARM format:
                          {"paramName": {"value": "paramValue"}, ...}

    Returns the deployment provisioning state and correlation ID.
    """
    DeploymentProperties = arm_client.models("2021-04-01").DeploymentProperties
    Deployment = arm_client.models("2021-04-01").Deployment

    properties = DeploymentProperties(
        mode="Incremental",
        template=arm_template,
        parameters=arm_parameters or {},
    )
    deployment = Deployment(properties=properties)

    poller = arm_client.deployments.begin_create_or_update(
        _rg(), deployment_name, deployment
    )
    result = poller.result()

    return json.dumps({
        "deployment":          deployment_name,
        "provisioning_state":  result.properties.provisioning_state,
        "correlation_id":      result.properties.correlation_id,
        "timestamp":           str(result.properties.timestamp),
        "duration":            result.properties.duration,
    }, indent=2)


@mcp.tool()
def get_deployment_status(deployment_name: str) -> str:
    """
    Check the status of an ARM deployment by name.
    Useful for monitoring long-running deployments kicked off with deploy_arm_template.
    """
    deployment = arm_client.deployments.get(_rg(), deployment_name)
    ops = list(arm_client.deployment_operations.list(_rg(), deployment_name))

    operations = []
    for op in ops:
        if op.properties:
            operations.append({
                "resource":           op.properties.target_resource.resource_name if op.properties.target_resource else None,
                "resource_type":      op.properties.target_resource.resource_type if op.properties.target_resource else None,
                "provisioning_state": op.properties.provisioning_state,
                "status_code":        op.properties.status_code,
                "status_message":     str(op.properties.status_message) if op.properties.status_message else None,
            })

    return json.dumps({
        "deployment":         deployment_name,
        "provisioning_state": deployment.properties.provisioning_state,
        "timestamp":          str(deployment.properties.timestamp),
        "operations":         operations,
    }, indent=2)


@mcp.tool()
def export_factory_arm_template() -> str:
    """
    Export the entire ADF factory as an ARM template.
    Returns the full ARM template JSON — useful for backup, migration,
    or deploying to another environment (e.g. TST → PRD).
    """
    result = adf_client.factories.get_data_plane_access(
        _rg(), _fn(),
        policy={"permissions": "r", "accessResourcePath": "/", "profileName": "null",
                "startTime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "expireTime": (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    )
    # Use ARM export directly
    export_result = arm_client.resource_groups.export_template(
        _rg(),
        {"resources": [f"/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/{_rg()}/providers/Microsoft.DataFactory/factories/{_fn()}"],
         "options": "IncludeParameterDefaultValue,IncludeComments"}
    )
    return json.dumps(export_result.template, indent=2)


# ══════════════════════════════════════════════════════════════════════════════
# ACTIVITY BUILDER TOOLS
# These tools return activity dicts (as JSON strings) ready to embed in the
# "activities" list when calling create_or_update_pipeline.
# All builders accept an optional depends_on list:
#   [{"activity": "<name>", "dependencyConditions": ["Succeeded"]}]
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def build_copy_activity(
    name: str,
    source_dataset: str,
    sink_dataset: str,
    source_type: str = "DelimitedTextSource",
    sink_type: str = "DelimitedTextSink",
    parallel_copies: Optional[int] = None,
    translator: Optional[dict] = None,
    enable_staging: bool = False,
    depends_on: Optional[list] = None,
) -> str:
    """
    Build a Copy Activity dict for use in create_or_update_pipeline.

    Args:
        name:             Activity name.
        source_dataset:   Source dataset reference name.
        sink_dataset:     Sink dataset reference name.
        source_type:      ADF source type e.g. DelimitedTextSource, SqlSource, ParquetSource, AzureSqlSource.
        sink_type:        ADF sink type e.g. DelimitedTextSink, SqlSink, ParquetSink, AzureSqlSink.
        parallel_copies:  Degree of copy parallelism (optional).
        translator:       Column mapping translator dict (optional).
        enable_staging:   Enable staged copy via Azure Blob (default False).
        depends_on:       Dependency list (optional).
    """
    activity: dict = {
        "name": name,
        "type": "Copy",
        "dependsOn": depends_on or [],
        "inputs":  [{"referenceName": source_dataset, "type": "DatasetReference"}],
        "outputs": [{"referenceName": sink_dataset,   "type": "DatasetReference"}],
        "typeProperties": {
            "source":        {"type": source_type},
            "sink":          {"type": sink_type},
            "enableStaging": enable_staging,
        },
    }
    if parallel_copies is not None:
        activity["typeProperties"]["parallelCopies"] = parallel_copies
    if translator:
        activity["typeProperties"]["translator"] = translator
    return json.dumps(activity, indent=2)


@mcp.tool()
def build_foreach_activity(
    name: str,
    items_expression: str,
    activities: list,
    is_sequential: bool = False,
    batch_count: int = 20,
    depends_on: Optional[list] = None,
) -> str:
    """
    Build a ForEach Activity dict.

    Args:
        name:              Activity name.
        items_expression:  ADF expression for the array to iterate e.g. "@pipeline().parameters.fileList".
        activities:        List of inner activity dicts (use other build_* tools to generate these).
        is_sequential:     Run iterations one-at-a-time (default False = parallel).
        batch_count:       Max parallel batches when not sequential (default 20, max 50).
        depends_on:        Dependency list (optional).
    """
    type_props: dict = {
        "items":       {"value": items_expression, "type": "Expression"},
        "isSequential": is_sequential,
        "activities":  activities,
    }
    if not is_sequential:
        type_props["batchCount"] = batch_count
    activity = {
        "name": name,
        "type": "ForEach",
        "dependsOn": depends_on or [],
        "typeProperties": type_props,
    }
    return json.dumps(activity, indent=2)


@mcp.tool()
def build_if_condition_activity(
    name: str,
    expression: str,
    if_true_activities: list,
    if_false_activities: Optional[list] = None,
    depends_on: Optional[list] = None,
) -> str:
    """
    Build an IfCondition Activity dict.

    Args:
        name:                  Activity name.
        expression:            Boolean ADF expression e.g. "@greater(pipeline().parameters.count, 0)".
        if_true_activities:    Activity dicts to run when expression is true.
        if_false_activities:   Activity dicts to run when expression is false (optional).
        depends_on:            Dependency list (optional).
    """
    activity = {
        "name": name,
        "type": "IfCondition",
        "dependsOn": depends_on or [],
        "typeProperties": {
            "expression":        {"value": expression, "type": "Expression"},
            "ifTrueActivities":  if_true_activities,
            "ifFalseActivities": if_false_activities or [],
        },
    }
    return json.dumps(activity, indent=2)


@mcp.tool()
def build_switch_activity(
    name: str,
    on_expression: str,
    cases: list,
    default_activities: Optional[list] = None,
    depends_on: Optional[list] = None,
) -> str:
    """
    Build a Switch Activity dict (multi-branch conditional).

    Args:
        name:               Activity name.
        on_expression:      ADF expression whose value selects a case e.g. "@variables('env')".
        cases:              List of case dicts: [{"value": "dev", "activities": [...]}, ...].
        default_activities: Activities to run when no case matches (optional).
        depends_on:         Dependency list (optional).
    """
    activity = {
        "name": name,
        "type": "Switch",
        "dependsOn": depends_on or [],
        "typeProperties": {
            "on":               {"value": on_expression, "type": "Expression"},
            "cases":            cases,
            "defaultActivities": default_activities or [],
        },
    }
    return json.dumps(activity, indent=2)


@mcp.tool()
def build_until_activity(
    name: str,
    expression: str,
    activities: list,
    timeout: str = "0.12:00:00",
    depends_on: Optional[list] = None,
) -> str:
    """
    Build an Until Activity dict (loops until expression evaluates to true).

    Args:
        name:        Activity name.
        expression:  Boolean ADF expression to stop the loop e.g. "@bool(variables('done'))".
        activities:  Inner activity dicts executed each iteration.
        timeout:     Max loop duration in d.HH:MM:SS format (default "0.12:00:00" = 12 hours).
        depends_on:  Dependency list (optional).
    """
    activity = {
        "name": name,
        "type": "Until",
        "dependsOn": depends_on or [],
        "typeProperties": {
            "expression": {"value": expression, "type": "Expression"},
            "activities": activities,
            "timeout":    timeout,
        },
    }
    return json.dumps(activity, indent=2)


@mcp.tool()
def build_filter_activity(
    name: str,
    items_expression: str,
    condition_expression: str,
    depends_on: Optional[list] = None,
) -> str:
    """
    Build a Filter Activity dict. Output: @activity('<name>').output.value (filtered array).

    Args:
        name:                 Activity name.
        items_expression:     ADF expression for the array to filter e.g. "@pipeline().parameters.files".
        condition_expression: ADF expression evaluated per item e.g. "@greater(item().size, 0)".
        depends_on:           Dependency list (optional).
    """
    activity = {
        "name": name,
        "type": "Filter",
        "dependsOn": depends_on or [],
        "typeProperties": {
            "items":     {"value": items_expression,     "type": "Expression"},
            "condition": {"value": condition_expression, "type": "Expression"},
        },
    }
    return json.dumps(activity, indent=2)


@mcp.tool()
def build_execute_pipeline_activity(
    name: str,
    pipeline_name: str,
    wait_on_completion: bool = True,
    parameters: Optional[dict] = None,
    depends_on: Optional[list] = None,
) -> str:
    """
    Build an ExecutePipeline Activity dict (invokes a child pipeline).

    Args:
        name:               Activity name.
        pipeline_name:      Name of the pipeline to execute.
        wait_on_completion: Wait for the child pipeline to finish before continuing (default True).
        parameters:         Dict of parameters to pass to the child pipeline.
        depends_on:         Dependency list (optional).
    """
    activity = {
        "name": name,
        "type": "ExecutePipeline",
        "dependsOn": depends_on or [],
        "policy": {"secureInput": False},
        "typeProperties": {
            "pipeline":           {"referenceName": pipeline_name, "type": "PipelineReference"},
            "waitOnCompletion":   wait_on_completion,
            "parameters":         parameters or {},
        },
    }
    return json.dumps(activity, indent=2)


@mcp.tool()
def build_lookup_activity(
    name: str,
    dataset_name: str,
    source_type: str = "DelimitedTextSource",
    query: Optional[str] = None,
    first_row_only: bool = True,
    depends_on: Optional[list] = None,
) -> str:
    """
    Build a Lookup Activity dict.
    Output accessible via @activity('<name>').output (firstRowOnly=true) or .output.value (false).

    Args:
        name:           Activity name.
        dataset_name:   Dataset reference name to look up from.
        source_type:    Source type e.g. DelimitedTextSource, AzureSqlSource, SqlSource.
        query:          Optional SQL query / ADF expression to filter results.
        first_row_only: Return only the first row (default True). False returns all rows as array.
        depends_on:     Dependency list (optional).
    """
    source: dict = {"type": source_type}
    if query:
        source["sqlReaderQuery"] = query
    activity = {
        "name": name,
        "type": "Lookup",
        "dependsOn": depends_on or [],
        "typeProperties": {
            "source":       source,
            "dataset":      {"referenceName": dataset_name, "type": "DatasetReference"},
            "firstRowOnly": first_row_only,
        },
    }
    return json.dumps(activity, indent=2)


@mcp.tool()
def build_get_metadata_activity(
    name: str,
    dataset_name: str,
    field_list: Optional[list] = None,
    depends_on: Optional[list] = None,
) -> str:
    """
    Build a GetMetadata Activity dict.
    Output accessible via @activity('<name>').output.<fieldName>.

    Args:
        name:          Activity name.
        dataset_name:  Dataset reference name.
        field_list:    Metadata fields to retrieve. Valid values: itemName, itemType,
                       lastModified, size, childItems, structure, columnCount, exists.
                       Defaults to ["itemName", "lastModified", "size"].
        depends_on:    Dependency list (optional).
    """
    activity = {
        "name": name,
        "type": "GetMetadata",
        "dependsOn": depends_on or [],
        "typeProperties": {
            "dataset":   {"referenceName": dataset_name, "type": "DatasetReference"},
            "fieldList": field_list or ["itemName", "lastModified", "size"],
        },
    }
    return json.dumps(activity, indent=2)


@mcp.tool()
def build_validation_activity(
    name: str,
    dataset_name: str,
    timeout: str = "0.12:00:00",
    sleep: int = 10,
    minimum_size: int = 0,
    child_items: Optional[int] = None,
    depends_on: Optional[list] = None,
) -> str:
    """
    Build a Validation Activity dict (waits/polls until a file or dataset exists).

    Args:
        name:          Activity name.
        dataset_name:  Dataset reference name to validate.
        timeout:       Max wait time in d.HH:MM:SS format (default "0.12:00:00" = 12 hours).
        sleep:         Polling interval in seconds (default 10).
        minimum_size:  Minimum file size in bytes for success (default 0).
        child_items:   Minimum number of child items required (folder datasets, optional).
        depends_on:    Dependency list (optional).
    """
    type_props: dict = {
        "dataset":     {"referenceName": dataset_name, "type": "DatasetReference"},
        "timeout":     timeout,
        "sleep":       sleep,
        "minimumSize": minimum_size,
    }
    if child_items is not None:
        type_props["childItems"] = child_items
    activity = {
        "name": name,
        "type": "Validation",
        "dependsOn": depends_on or [],
        "typeProperties": type_props,
    }
    return json.dumps(activity, indent=2)


@mcp.tool()
def build_delete_activity(
    name: str,
    dataset_name: str,
    store_settings_type: str = "AzureBlobStorageReadSettings",
    recursive: bool = False,
    max_concurrent_connections: int = 1,
    enable_logging: bool = False,
    depends_on: Optional[list] = None,
) -> str:
    """
    Build a Delete Activity dict (deletes files or rows from a store).

    Args:
        name:                        Activity name.
        dataset_name:                Dataset reference name pointing to what to delete.
        store_settings_type:         Store settings type e.g. AzureBlobStorageReadSettings,
                                     AzureDataLakeStoreReadSettings, AmazonS3ReadSettings.
        recursive:                   Delete files recursively (default False).
        max_concurrent_connections:  Parallelism (default 1).
        enable_logging:              Log deleted file names to a storage account (default False).
        depends_on:                  Dependency list (optional).
    """
    activity = {
        "name": name,
        "type": "Delete",
        "dependsOn": depends_on or [],
        "typeProperties": {
            "dataset":      {"referenceName": dataset_name, "type": "DatasetReference"},
            "enableLogging": enable_logging,
            "storeSettings": {
                "type":                      store_settings_type,
                "recursive":                 recursive,
                "maxConcurrentConnections":  max_concurrent_connections,
            },
        },
    }
    return json.dumps(activity, indent=2)


@mcp.tool()
def build_stored_procedure_activity(
    name: str,
    linked_service_name: str,
    stored_procedure_name: str,
    stored_procedure_parameters: Optional[dict] = None,
    depends_on: Optional[list] = None,
) -> str:
    """
    Build a Stored Procedure Activity dict.

    Args:
        name:                          Activity name.
        linked_service_name:           SQL linked service reference name.
        stored_procedure_name:         Name of the stored procedure to execute.
        stored_procedure_parameters:   Dict of parameters e.g.
                                       {"param1": {"value": "val1", "type": "String"}}.
        depends_on:                    Dependency list (optional).
    """
    activity = {
        "name": name,
        "type": "SqlServerStoredProcedure",
        "dependsOn": depends_on or [],
        "linkedServiceName": {"referenceName": linked_service_name, "type": "LinkedServiceReference"},
        "typeProperties": {
            "storedProcedureName":       stored_procedure_name,
            "storedProcedureParameters": stored_procedure_parameters or {},
        },
    }
    return json.dumps(activity, indent=2)


@mcp.tool()
def build_script_activity(
    name: str,
    linked_service_name: str,
    scripts: list,
    script_block_execution_timeout: str = "02:00:00",
    depends_on: Optional[list] = None,
) -> str:
    """
    Build a Script Activity dict (runs SQL/T-SQL blocks against a linked service).

    Args:
        name:                             Activity name.
        linked_service_name:              SQL / Synapse linked service reference name.
        scripts:                          List of script block dicts:
                                          [{"type": "Query", "text": "TRUNCATE TABLE dbo.stg"}, ...]
                                          type is "Query" (returns rows) or "NonQuery" (DDL/DML).
        script_block_execution_timeout:   Per-block timeout in HH:MM:SS (default "02:00:00").
        depends_on:                       Dependency list (optional).
    """
    activity = {
        "name": name,
        "type": "Script",
        "dependsOn": depends_on or [],
        "linkedServiceName": {"referenceName": linked_service_name, "type": "LinkedServiceReference"},
        "typeProperties": {
            "scripts":                      scripts,
            "scriptBlockExecutionTimeout":  script_block_execution_timeout,
        },
    }
    return json.dumps(activity, indent=2)


@mcp.tool()
def build_web_activity(
    name: str,
    url: str,
    method: str = "GET",
    headers: Optional[dict] = None,
    body: Optional[dict] = None,
    linked_service_name: Optional[str] = None,
    depends_on: Optional[list] = None,
) -> str:
    """
    Build a Web Activity dict (calls an HTTP/REST endpoint).

    Args:
        name:                 Activity name.
        url:                  HTTP endpoint URL or ADF expression.
        method:               HTTP method: GET | POST | PUT | DELETE (default GET).
        headers:              Dict of HTTP headers (optional).
        body:                 Request body dict (optional, used with POST/PUT).
        linked_service_name:  Linked service for authentication (optional).
        depends_on:           Dependency list (optional).
    """
    type_props: dict = {
        "url":     url,
        "method":  method.upper(),
        "headers": headers or {},
    }
    if body:
        type_props["body"] = body
    if linked_service_name:
        type_props["linkedServices"] = [
            {"referenceName": linked_service_name, "type": "LinkedServiceReference"}
        ]
    activity = {
        "name": name,
        "type": "WebActivity",
        "dependsOn": depends_on or [],
        "typeProperties": type_props,
    }
    return json.dumps(activity, indent=2)


@mcp.tool()
def build_azure_function_activity(
    name: str,
    azure_function_linked_service: str,
    function_name: str,
    method: str = "POST",
    headers: Optional[dict] = None,
    body: Optional[dict] = None,
    depends_on: Optional[list] = None,
) -> str:
    """
    Build an Azure Function Activity dict.

    Args:
        name:                           Activity name.
        azure_function_linked_service:  Azure Function App linked service reference name.
        function_name:                  Name of the Azure Function to invoke.
        method:                         HTTP method: GET | POST | PUT | DELETE (default POST).
        headers:                        Dict of HTTP headers (optional).
        body:                           Request body dict (optional).
        depends_on:                     Dependency list (optional).
    """
    activity = {
        "name": name,
        "type": "AzureFunctionActivity",
        "dependsOn": depends_on or [],
        "linkedServiceName": {"referenceName": azure_function_linked_service, "type": "LinkedServiceReference"},
        "typeProperties": {
            "functionName": function_name,
            "method":       method.upper(),
            "headers":      headers or {},
            "body":         body or {},
        },
    }
    return json.dumps(activity, indent=2)


@mcp.tool()
def build_databricks_notebook_activity(
    name: str,
    linked_service_name: str,
    notebook_path: str,
    base_parameters: Optional[dict] = None,
    libraries: Optional[list] = None,
    depends_on: Optional[list] = None,
) -> str:
    """
    Build a Databricks Notebook Activity dict.

    Args:
        name:                 Activity name.
        linked_service_name:  Databricks linked service reference name.
        notebook_path:        Absolute Databricks workspace path e.g. "/Workspace/MyProject/etl".
        base_parameters:      Dict of notebook widget parameters e.g. {"env": "tst", "date": "@utcNow()"}.
        libraries:            List of library install dicts e.g. [{"pypi": {"package": "pandas"}}].
        depends_on:           Dependency list (optional).
    """
    activity = {
        "name": name,
        "type": "DatabricksNotebook",
        "dependsOn": depends_on or [],
        "linkedServiceName": {"referenceName": linked_service_name, "type": "LinkedServiceReference"},
        "typeProperties": {
            "notebookPath":   notebook_path,
            "baseParameters": base_parameters or {},
            "libraries":      libraries or [],
        },
    }
    return json.dumps(activity, indent=2)


@mcp.tool()
def build_databricks_python_activity(
    name: str,
    linked_service_name: str,
    python_file: str,
    parameters: Optional[list] = None,
    libraries: Optional[list] = None,
    depends_on: Optional[list] = None,
) -> str:
    """
    Build a Databricks Python Activity dict (runs a .py script on a Databricks cluster).

    Args:
        name:                 Activity name.
        linked_service_name:  Databricks linked service reference name.
        python_file:          DBFS path to the Python script e.g. "dbfs:/scripts/transform.py".
        parameters:           List of string CLI arguments e.g. ["--env", "tst", "--date", "2026-06-01"].
        libraries:            List of library install dicts e.g. [{"pypi": {"package": "great_expectations"}}].
        depends_on:           Dependency list (optional).
    """
    activity = {
        "name": name,
        "type": "DatabricksPython",
        "dependsOn": depends_on or [],
        "linkedServiceName": {"referenceName": linked_service_name, "type": "LinkedServiceReference"},
        "typeProperties": {
            "pythonFile":  python_file,
            "parameters":  parameters or [],
            "libraries":   libraries or [],
        },
    }
    return json.dumps(activity, indent=2)


@mcp.tool()
def build_set_variable_activity(
    name: str,
    variable_name: str,
    value_expression: str,
    depends_on: Optional[list] = None,
) -> str:
    """
    Build a SetVariable Activity dict.

    Args:
        name:              Activity name.
        variable_name:     Pipeline variable name to set.
        value_expression:  ADF expression or literal value e.g. "@utcNow()" or "hello".
        depends_on:        Dependency list (optional).
    """
    activity = {
        "name": name,
        "type": "SetVariable",
        "dependsOn": depends_on or [],
        "typeProperties": {
            "variableName": variable_name,
            "value":        {"value": value_expression, "type": "Expression"},
        },
    }
    return json.dumps(activity, indent=2)


@mcp.tool()
def build_append_variable_activity(
    name: str,
    variable_name: str,
    value_expression: str,
    depends_on: Optional[list] = None,
) -> str:
    """
    Build an AppendVariable Activity dict (appends a value to an array-type pipeline variable).

    Args:
        name:              Activity name.
        variable_name:     Array-type pipeline variable name to append to.
        value_expression:  ADF expression or value to append e.g. "@item().fileName".
        depends_on:        Dependency list (optional).
    """
    activity = {
        "name": name,
        "type": "AppendVariable",
        "dependsOn": depends_on or [],
        "typeProperties": {
            "variableName": variable_name,
            "value":        {"value": value_expression, "type": "Expression"},
        },
    }
    return json.dumps(activity, indent=2)


@mcp.tool()
def build_wait_activity(
    name: str,
    wait_time_in_seconds: int,
    depends_on: Optional[list] = None,
) -> str:
    """
    Build a Wait Activity dict (pauses pipeline execution for a fixed duration).

    Args:
        name:                  Activity name.
        wait_time_in_seconds:  Number of seconds to pause (max 604800 = 7 days).
        depends_on:            Dependency list (optional).
    """
    activity = {
        "name": name,
        "type": "Wait",
        "dependsOn": depends_on or [],
        "typeProperties": {
            "waitTimeInSeconds": wait_time_in_seconds,
        },
    }
    return json.dumps(activity, indent=2)


@mcp.tool()
def build_fail_activity(
    name: str,
    message_expression: str,
    error_code_expression: str = "500",
    depends_on: Optional[list] = None,
) -> str:
    """
    Build a Fail Activity dict (explicitly fails the pipeline with a custom error message).

    Args:
        name:                   Activity name.
        message_expression:     Error message or ADF expression e.g. "Validation failed for @{pipeline().parameters.file}".
        error_code_expression:  Error code string or ADF expression (default "500").
        depends_on:             Dependency list (optional).
    """
    activity = {
        "name": name,
        "type": "Fail",
        "dependsOn": depends_on or [],
        "typeProperties": {
            "message":   {"value": message_expression,   "type": "Expression"},
            "errorCode": {"value": error_code_expression, "type": "Expression"},
        },
    }
    return json.dumps(activity, indent=2)


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    mcp.run(transport="stdio")
