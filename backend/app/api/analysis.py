from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core import storage
from app.modules.keypoints import service as keypoints
from app.modules.qa import service as qa
from app.modules.questions import service as questions

router = APIRouter(prefix="/api/documents", tags=["analysis"])


class QuestionRequest(BaseModel):
    # 数量/题型合法性由 service 统一校验，保证返回稳定的 INVALID_COUNT / INVALID_TYPES 码
    count: int = 5
    types: list[str] = Field(default=["single"])
    difficulty: str | None = Field(default=None, max_length=20)
    cognitive: str | None = Field(default=None, max_length=20)
    chapters: list[str] = Field(default=[], max_length=12)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[dict[str, str]] = Field(default=[])


@router.post("/{doc_id}/key-points")
def key_points(doc_id: str):
    return keypoints.generate(storage.load_document(doc_id))


@router.post("/{doc_id}/questions")
def gen_questions(doc_id: str, req: QuestionRequest):
    return questions.generate(storage.load_document(doc_id), req.model_dump())


@router.post("/{doc_id}/chat")
def chat(doc_id: str, req: ChatRequest):
    return qa.answer(
        storage.load_document(doc_id), req.question.strip(), req.history
    )
