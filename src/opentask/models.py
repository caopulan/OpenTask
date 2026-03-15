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
ControlActionKind = Literal[
    "pause",
    "resume",
    "retry",
    "skip",
    "approve",
    "send_message",
    "patch_cron",
]


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


class DeliveryContext(OpenTaskModel):
    channel: str | None = None
    to: str | None = None
    account_id: str | None = Field(default=None, alias="accountId")
    thread_id: str | None = Field(default=None, alias="threadId")


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
    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
        str_strip_whitespace=True,
    )

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
    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
        str_strip_whitespace=True,
    )

    run_id: str = Field(alias="runId")
    workflow_id: str = Field(alias="workflowId")
    title: str
    status: RunStatus
    source_session_key: str | None = Field(default=None, alias="sourceSessionKey")
    source_agent_id: str | None = Field(default=None, alias="sourceAgentId")
    delivery_context: DeliveryContext | None = Field(default=None, alias="deliveryContext")
    root_session_key: str | None = Field(default=None, alias="rootSessionKey")
    planner_session_key: str | None = Field(default=None, alias="plannerSessionKey")
    driver_session_key: str | None = Field(default=None, alias="driverSessionKey")
    cron_job_id: str | None = Field(default=None, alias="cronJobId")
    updated_at: str = Field(default_factory=utc_now, alias="updatedAt")
    created_at: str = Field(default_factory=utc_now, alias="createdAt")
    nodes: list[NodeState]
    last_event: str | None = Field(default=None, alias="lastEvent")
    last_progress_message: str | None = Field(default=None, alias="lastProgressMessage")
    last_progress_message_at: str | None = Field(default=None, alias="lastProgressMessageAt")

    @model_validator(mode="after")
    def normalize_session_fields(self) -> "RunState":
        root_session_key = self.root_session_key or self.driver_session_key or self.planner_session_key or self.source_session_key
        if not root_session_key:
            raise ValueError("run requires rootSessionKey or driverSessionKey")
        if self.root_session_key is None:
            self.root_session_key = root_session_key
        if self.driver_session_key is None:
            self.driver_session_key = root_session_key
        if self.planner_session_key is None:
            self.planner_session_key = root_session_key
        if self.source_agent_id is None and self.source_session_key and self.source_session_key.startswith("agent:"):
            parts = self.source_session_key.split(":")
            if len(parts) > 1:
                self.source_agent_id = parts[1]
        return self


class RunEvent(OpenTaskModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
        str_strip_whitespace=True,
    )

    event: str
    run_id: str = Field(alias="runId")
    timestamp: str = Field(default_factory=utc_now)
    node_id: str | None = Field(default=None, alias="nodeId")
    message: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class RunRefs(OpenTaskModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
        str_strip_whitespace=True,
    )

    run_id: str | None = Field(default=None, alias="runId")
    source_session_key: str | None = Field(default=None, alias="sourceSessionKey")
    source_agent_id: str | None = Field(default=None, alias="sourceAgentId")
    delivery_context: DeliveryContext | None = Field(default=None, alias="deliveryContext")
    root_session_key: str | None = Field(default=None, alias="rootSessionKey")
    planner_session_key: str | None = Field(default=None, alias="plannerSessionKey")
    driver_session_key: str | None = Field(default=None, alias="driverSessionKey")
    cron_job_id: str | None = Field(default=None, alias="cronJobId")
    driver_run_id: str | None = Field(default=None, alias="driverRunId")
    driver_requested_event_count: int = Field(default=0, alias="driverRequestedEventCount")
    driver_requested_activity_count: int = Field(default=0, alias="driverRequestedActivityCount")
    node_sessions: dict[str, str] = Field(default_factory=dict, alias="nodeSessions")
    child_sessions: dict[str, str] = Field(default_factory=dict, alias="childSessions")
    node_run_ids: dict[str, str] = Field(default_factory=dict, alias="nodeRunIds")
    applied_control_ids: list[str] = Field(default_factory=list, alias="appliedControlIds")
    last_progress_event_count: int = Field(default=0, alias="lastProgressEventCount")

    @model_validator(mode="after")
    def normalize_session_fields(self) -> "RunRefs":
        root_session_key = self.root_session_key or self.driver_session_key or self.planner_session_key or self.source_session_key
        if root_session_key:
            if self.root_session_key is None:
                self.root_session_key = root_session_key
            if self.driver_session_key is None:
                self.driver_session_key = root_session_key
            if self.planner_session_key is None:
                self.planner_session_key = root_session_key
        if self.source_agent_id is None and self.source_session_key and self.source_session_key.startswith("agent:"):
            parts = self.source_session_key.split(":")
            if len(parts) > 1:
                self.source_agent_id = parts[1]
        return self


OpenClawRefs = RunRefs


class CreateRunRequest(OpenTaskModel):
    workflow_path: str | None = Field(default=None, alias="workflowPath")
    workflow_markdown: str | None = Field(default=None, alias="workflowMarkdown")
    task_text: str | None = Field(default=None, alias="taskText")
    title: str | None = None
    source_session_key: str | None = Field(default=None, alias="sourceSessionKey")
    source_agent_id: str | None = Field(default=None, alias="sourceAgentId")
    delivery_context: DeliveryContext | None = Field(default=None, alias="deliveryContext")
    root_session_key: str | None = Field(default=None, alias="rootSessionKey")


class RunActionRequest(OpenTaskModel):
    node_id: str | None = Field(default=None, alias="nodeId")
    message: str | None = None
    patch: dict[str, Any] = Field(default_factory=dict)


NodeActionRequest = RunActionRequest


class RunControlAction(OpenTaskModel):
    id: str
    action: ControlActionKind
    run_id: str = Field(alias="runId")
    timestamp: str = Field(default_factory=utc_now)
    node_id: str | None = Field(default=None, alias="nodeId")
    message: str | None = None
    patch: dict[str, Any] = Field(default_factory=dict)


class NodeResult(OpenTaskModel):
    run_id: str = Field(alias="runId")
    node_id: str = Field(alias="nodeId")
    status: NodeStatus
    summary: str | None = None
    artifacts: list[str] = Field(default_factory=list)
    session_key: str | None = Field(default=None, alias="sessionKey")
    child_session_key: str | None = Field(default=None, alias="childSessionKey")
    payload: dict[str, Any] = Field(default_factory=dict)


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
