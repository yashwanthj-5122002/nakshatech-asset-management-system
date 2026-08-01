from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    role: str | None = None


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    role: str
    branch: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
