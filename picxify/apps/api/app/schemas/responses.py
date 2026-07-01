import uuid

from pydantic import BaseModel


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    name: str | None


class WorkspaceSummary(BaseModel):
    id: uuid.UUID
    name: str
    slug: str | None
    role: str


class UserSyncResponse(BaseModel):
    user: UserResponse
    workspaces: list[WorkspaceSummary]
    created: bool


class WorkspaceListResponse(BaseModel):
    workspaces: list[WorkspaceSummary]
