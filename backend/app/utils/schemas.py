from typing import List, Dict, Any

from pydantic import BaseModel, Field

class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=6, max_length=128)

class UserLogin(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    username: str

class UserInfoResponse(BaseModel):
    user_id: int
    username: str

class LogoutResponse(BaseModel):
    message: str

class PipelineSave(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    nodes: List[Dict[str, Any]]
    branchSources: Dict[str, str] | None = None

class PipelineResponse(BaseModel):
    id: int
    name: str
    pipeline_data: Dict[str, Any]

class PipelineListItem(BaseModel):
    id: int
    name: str