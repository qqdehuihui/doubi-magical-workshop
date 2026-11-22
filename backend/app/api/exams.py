"""历年考试资料库 API（上传试卷/题库/提纲、列表、删除、高频考点统计）。"""

from fastapi import APIRouter, File, Form, Query, UploadFile

from app.core.errors import ApiException
from app.modules.examdb import service

router = APIRouter(prefix="/api/exams", tags=["exams"])


@router.post("")
async def upload_exam(
    file: UploadFile = File(...),
    course_id: str | None = Form(default=None, max_length=100),
    material_type: str | None = Form(default=None, max_length=30),
    year: int | None = Form(default=None, ge=1900, le=2100),
):
    data = await file.read()
    return service.upload_exam(data, file.filename or "untitled", course_id, material_type, year)


@router.get("")
def list_exams(course_id: str | None = Query(default=None, max_length=100)):
    return service.list_exams((course_id or "").strip() or None)


@router.get("/frequent-points")
def frequent_points(
    course_id: str = Query(default="default", max_length=100),
    doc_id: str | None = Query(default=None, max_length=64),
):
    if doc_id is not None and not (len(doc_id) == 32 and all(c in "0123456789abcdef" for c in doc_id)):
        raise ApiException("DOC_NOT_FOUND", "文档不存在或已过期，请重新上传", 404)
    return service.frequent_points((course_id or "default").strip() or "default", doc_id)


@router.delete("/{exam_doc_id}")
def delete_exam(exam_doc_id: str):
    return service.delete_exam(exam_doc_id)
