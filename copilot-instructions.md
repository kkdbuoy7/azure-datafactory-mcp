# ADF MCP Server — Copilot Behaviour Instructions

These rules apply whenever GitHub Copilot is using the ADF MCP tools.

---

## 1. End-to-End Pipeline Requests — Plan First, Build Second

When a user asks to **build**, **create**, or **set up** a pipeline (especially end-to-end or multi-step ones):

1. **Plan first.** Before calling any MCP tool, produce a clear written plan that includes:
   - The pipeline name (including the user's initials as a prefix, e.g. `ST_MyPipeline`)
   - The logical steps / activities in order (Copy, ForEach, Lookup, etc.)
   - Any dependencies between activities
   - Parameters or variables the pipeline will use
   - Datasets, linked services, and triggers involved

2. **Wait for explicit confirmation.** After presenting the plan, ask:
   > "Does this plan look correct? Should I go ahead and build it?"
   Do **not** start creating any ADF resources until the user says yes.

3. **Build incrementally.** Once confirmed, create resources in dependency order:
   linked services → datasets → pipeline → trigger (if requested).
   Confirm each major step with the user before proceeding to the next.

---

## 2. Reuse Before Creating — Always Check Existing Resources First

Before creating any **dataset**, **linked service**, or **trigger**, always check what already exists:

1. Call `list_linked_services` and `list_datasets` (and `list_triggers` if a trigger is needed).
2. For any candidate item, call `get_linked_service_definition` / `get_dataset_definition` / `get_trigger_definition` to inspect its configuration.
3. **Reuse** an existing item if it matches the user's requirement (same connection, same format, same storage location, etc.). Tell the user which existing resource you are reusing and why.
4. Only create a **new** resource when no existing one is suitable — and explain why none of the existing ones fit.

### Also check Global Parameters

If the pipeline logic involves environment-specific values (storage URLs, container names, schema names, etc.), inspect the factory's existing pipelines for any global parameter patterns already in use. Align new items with those conventions.

---

## 3. General Rules

- Always name new resources with the **user's initials as a segment** in the name (e.g. `ST_Dataset_Blob`, `ST_Trigger_Daily`). The server will reject names that don't comply.
- Never delete pipelines, datasets, linked services, or triggers. Those tools have been removed for safety.
- When in doubt about a user's intent, ask a clarifying question rather than making assumptions.
