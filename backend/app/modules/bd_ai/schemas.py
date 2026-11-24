
from pydantic import BaseModel, Field


class BDAIContext(BaseModel):
    client_name: str = Field(default="", max_length=160)
    project_reference: str = Field(default="", max_length=160)
    department: str = Field(default="", max_length=100)
    requirements: str = Field(min_length=20, max_length=10000)


class BDAIAnalysis(BaseModel):
    project_objective: str
    scope_of_work: str
    expected_deliverables: list[str]
    technical_specifications: list[str]
    constraints_deadline: str
    missing_information: list[str]
    clarification_questions: list[str]
    confirmed_requirements: list[str]
    acceptance_criteria: list[str]
    department_handover_notes: list[str]


class BDAIAnswer(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    answer: str = Field(min_length=1, max_length=2000)


class BDAIRefineRequest(BaseModel):
    context: BDAIContext
    previous: BDAIAnalysis
    answers: list[BDAIAnswer] = Field(min_length=1, max_length=8)
