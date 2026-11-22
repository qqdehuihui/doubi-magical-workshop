import type {
  ChatMessage,
  ChatReply,
  Cognitive,
  Difficulty,
  DocumentMeta,
  ExamUploadResult,
  FrequentStats,
  KeyPointsResult,
  QuestionType,
  QuestionsResult,
} from './types'

export const MAX_FILE_MB = 50
const SUPPORTED = ['.pdf', '.pptx', '.docx']
const LEGACY = ['.ppt', '.doc']

export class ApiError extends Error {
  code: string
  constructor(code: string, message: string) {
    super(message)
    this.code = code
  }
}

async function request<T>(input: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(input, init)
  } catch {
    throw new ApiError('NETWORK_ERROR', '无法连接后端服务，请确认后端已启动')
  }
  if (!res.ok) {
    let body: { code?: string; message?: string } | null = null
    try {
      body = await res.json()
    } catch {
      /* 非 JSON 错误体 */
    }
    throw new ApiError(body?.code ?? `HTTP_${res.status}`, body?.message ?? `请求失败（${res.status}）`)
  }
  return res.json() as Promise<T>
}

function clientCheck(file: File) {
  const name = file.name.toLowerCase()
  if (LEGACY.some((ext) => name.endsWith(ext))) {
    throw new ApiError('UNSUPPORTED_FORMAT', '暂不支持旧版 .ppt / .doc，请在 Office/WPS 中「另存为」.pptx 或 .docx 后上传')
  }
  if (!SUPPORTED.some((ext) => name.endsWith(ext))) {
    throw new ApiError('UNSUPPORTED_FORMAT', '目前仅支持 PDF（.pdf）、PowerPoint（.pptx）、Word（.docx）三种格式')
  }
  if (file.size === 0) throw new ApiError('EMPTY_FILE', '文件为空，请检查后重新上传')
  if (file.size > MAX_FILE_MB * 1024 * 1024) {
    throw new ApiError('FILE_TOO_LARGE', `文件超过 ${MAX_FILE_MB}MB 限制`)
  }
}

function upload<T>(url: string, file: File, extra: Record<string, string>, onProgress?: (pct: number) => void): Promise<T> {
  clientCheck(file)
  return new Promise<T>((resolve, reject) => {
    const form = new FormData()
    form.append('file', file)
    for (const [k, v] of Object.entries(extra)) if (v) form.append(k, v)
    const xhr = new XMLHttpRequest()
    xhr.open('POST', url)
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100))
    }
    xhr.onload = () => {
      let body: unknown = null
      try {
        body = JSON.parse(xhr.responseText)
      } catch {
        /* 非 JSON 响应 */
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body as T)
      } else {
        const b = body as { code?: string; message?: string } | null
        reject(new ApiError(b?.code ?? `HTTP_${xhr.status}`, b?.message ?? `上传失败（${xhr.status}）`))
      }
    }
    xhr.onerror = () => reject(new ApiError('NETWORK_ERROR', '无法连接后端服务，请确认后端已启动'))
    xhr.send(form)
  })
}

export function uploadDocument(file: File, courseId?: string, onProgress?: (pct: number) => void) {
  return upload<DocumentMeta>('/api/documents', file, { course_id: courseId ?? '' }, onProgress)
}

export const getKeyPoints = (docId: string) =>
  request<KeyPointsResult>(`/api/documents/${docId}/key-points`, { method: 'POST' })

export interface QuestionParams {
  count: number
  types: QuestionType[]
  difficulty?: Difficulty | null
  cognitive?: Cognitive | null
  chapters?: string[]
}

export const generateQuestions = (docId: string, params: QuestionParams) =>
  request<QuestionsResult>(`/api/documents/${docId}/questions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })

export const sendChat = (docId: string, question: string, history: ChatMessage[]) =>
  request<ChatReply>(`/api/documents/${docId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, history }),
  })

export function uploadExam(file: File, meta: { course_id: string; material_type: string; year: string }, onProgress?: (pct: number) => void) {
  return upload<ExamUploadResult>('/api/exams', file, { course_id: meta.course_id, material_type: meta.material_type, year: meta.year }, onProgress)
}

export const listExams = (courseId?: string) =>
  request<{ exams: import('./types').ExamMeta[]; exam_count: number }>(`/api/exams${courseId ? `?course_id=${encodeURIComponent(courseId)}` : ''}`)

export const getFrequentPoints = (courseId: string) =>
  request<FrequentStats>(`/api/exams/frequent-points?course_id=${encodeURIComponent(courseId)}`)

export const deleteExam = (examDocId: string) =>
  request<{ deleted: string }>(`/api/exams/${examDocId}`, { method: 'DELETE' })
