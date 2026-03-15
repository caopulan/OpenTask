from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

NodeKind = Literal["session_turn", "subagent", "wait", "approval", "summary"]
OutputMode = Literal["notify", "report"]
NodeStatus = Literal["pending", "ready", "running", "waiting", "completed", "failed", "skipped"]
RunStatus = Literal["draft", "running", "paused", "completed", "failed", "cancelled"]
MutationKind = Literal["add_node", "rewire_node"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_workflow_agent_id() -> str:
    return os.getenv("OPENTASK_AGENT_ID", "opentask").strip() or "opentask"


class OpenTaskModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
    )


class WorkflowOutputs(OpenTaskModel):
    mode: OutputMode
    path: str | None = None
    required_files: list[str] = Field(default_factory=list, alias="requiredFiles")


class WaitCondition(OpenTaskModel):
    type: Literal["next_tick", "manual", "file_exists"] = "manual"
    path: str | None = None

    @model_validator(mode="after")
    def validate_path(self) -> "WaitCondition":
        if self.type == "file_exists" and not self.path:
            raise ValueError("waitFor.path is required when waitFor.type=file_exists")
        return self


class WorkflowNode(OpenTaskModel):
    id: str
    title: str
    kind: NodeKind
    needs: list[str] = Field(default_factory=list)
    prompt: str = ""
    outputs: WorkflowOutputs
    timeout_ms: int | None = Field(default=None, alias="timeoutMs")
    session_key: str | None = Field(default=None, alias="sessionKey")
    wait_for: WaitCondition | None = Field(default=None, alias="waitFor")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_prompt_and_wait(self) -> "WorkflowNode":
        if self.kind in {"session_turn", "subagent"} and not self.prompt:
            raise ValueError(f"node {self.id} requires prompt for kind={self.kind}")
        if self.kind == "wait" and self.wait_for is None:
            self.wait_for = WaitCondition()
        return self


class WorkflowDefaults(OpenTaskModel):
    agent_id: str = Field(default_factory=_default_workflow_agent_id, alias="agentId")
    model: str | None = None
    thinking: str | None = None
    timeout_ms: int = Field(default=30_000, alias="timeoutMs")


class DriverConfig(OpenTaskModel):
    cron: str = "*/2 * * * *"
    timeout_ms: int = Field(default=45_000, alias="timeoutMs")
    wake_mode: Literal["now", "next-heartbeat"] = Field(default="now", alias="wakeMode")
    session_key_template: str = Field(
        default="session:workflow:{run_id}:driver",
        alias="sessionKeyTemplate",
    )
    planner_session_key_template: str = Field(
        default="session:workflow:{run_id}:planner",
        alias="plannerSessionKeyTemplate",
    )


class WorkflowDefinition(OpenTaskModel):
    workflow_id: str = Field(alias="workflowId")
    title: str
    defaults: WorkflowDefaults = Field(default_factory=WorkflowDefaults)
    driver: DriverConfig = Field(default_factory=DriverConfig)
    nodes: list[WorkflowNode]


class ParsedWorkflow(OpenTaskModel):
    definition: WorkflowDefinition
    body: str = ""
    source_path: str | None = Field(default=None, alias="sourcePath")


class NodeState(OpenTaskModel):
    id: str
    title: str
    kind: NodeKind
    status: NodeStatus = "pending"
    needs: list[str] = Field(default_factory=list)
    outputs_mode: OutputMode = Field(alias="outputsMode")
    session_key: str | None = Field(default=None, alias="sessionKey")
    child_session_key: str | None = Field(default=None, alias="childSessionKey")
    run_id: str | None = Field(default=None, alias="runId")
    artifact_paths: list[str] = Field(default_factory=list, alias="artifactPaths")
    notes: list[str] = Field(default_factory=list)
    started_at: str | None = Field(default=None, alias="startedAt")
    completed_at: str | None = Field(default=None, alias="completedAt")
    wait_for: WaitCondition | None = Field(default=None, alias="waitFor")


class RunState(OpenTaskModel):
    run_id: str = Field(alias="runId")
    workflow_id: str = Field(alias="workflowId")
    title: str
    status: RunStatus
    planner_session_key: str = Field(alias="plannerSessionKey")
    driver_session_key: str = Field(alias="driverSessionKey")
    cron_job_id: str | None = Field(default=None, alias="cronJobId")
    updated_at: str = Field(default_factory=utc_now, alias="updatedAt")
    created_at: str = Field(default_factory=utc_now, alias="createdAt")
    nodes: list[NodeState]
    last_event: str | None = Field(default=None, alias="lastEvent")


class RunEvent(OpenTaskModel):
    event: str
    run_id: str = Field(alias="runId")
    timestamp: str = Field(default_factory=utc_now)
    node_id: str | None = Field(default=None, alias="nodeId")
    message: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class OpenClawRefs(OpenTaskModel):
    planner_session_key: str = Field(alias="plannerSessionKey")
    driver_session_key: str = Field(alias="driverSessionKey")
    cron_job_id: str | None = Field(default=None, alias="cronJobId")
    driver_run_id: str | None = Field(default=None, alias="driverRunId")
    driver_requested_event_count: int = Field(default=0, alias="driverRequestedEventCount")
    node_sessions: dict[str, str] = Field(default_factory=dict, alias="nodeSessions")
    child_sessions: dict[str, str] = Field(default_factory=dict, alias="childSessions")
    node_run_ids: dict[str, str] = Field(default_factory=dict, alias="nodeRunIds")


class CreateRunRequest(OpenTaskModel):
    workflow_path: str | None = Field(default=None, alias="workflowPath")
    workflow_markdown: str | None = Field(default=None, alias="workflowMarkdown")
    task_text: str | None = Field(default=None, alias="taskText")
    title: str | None = None


class NodeActionRequest(OpenTaskModel):
    node_id: str | None = Field(default=None, alias="nodeId")


class AddNodeMutation(OpenTaskModel):
    kind: Literal["add_node"] = "add_node"
    node: WorkflowNode


class RewireNodeMutation(OpenTaskModel):
    kind: Literal["rewire_node"] = "rewire_node"
    node_id: str = Field(alias="nodeId")
    needs: list[str] = Field(default_factory=list)


WorkflowMutation = Annotated[AddNodeMutation | RewireNodeMutation, Field(discriminator="kind")]
WORKFLOW_MUTATION_ADAPTER = TypeAdapter(WorkflowMutation)


class DriverMutationDirective(OpenTaskModel):
    id: str
    summary: str | None = None
    mutations: list[WorkflowMutation]
