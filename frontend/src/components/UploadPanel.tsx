import { useRef, useState } from 'react'
import { ApiError, uploadDocument } from '../api'
import type { DocumentMeta } from '../types'
import { FILE_TYPE_LABELS } from '../types'

interface Props {
  onUploaded: (doc: DocumentMeta) => void
  current: DocumentMeta | null
}

export default function UploadPanel({ onUploaded, current }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [pct, setPct] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [course, setCourse] = useState('')

  async function handleFile(file: File | undefined) {
    if (!file) return
    setBusy(true)
    setError(null)
    setPct(0)
    try {
      onUploaded(await uploadDocument(file, course.trim(), setPct))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '上传失败，请重试')
    } finally {
      setBusy(false)
      setPct(null)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  return (
    <section className="card upload-card">
      <div className="upload-row">
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.pptx,.docx,application/pdf"
          onChange={(e) => handleFile(e.target.files?.[0])}
          disabled={busy}
        />
        <input className="course-input" placeholder="课程标识（可选，用于关联历年试卷）" value={course} onChange={(e) => setCourse(e.target.value)} disabled={busy} />
        <button className="primary" onClick={() => handleFile(inputRef.current?.files?.[0])} disabled={busy}>
          {busy ? '解析中…' : '上传并解析'}
        </button>
      </div>
      {busy && pct !== null && (
        <div className="progress">
          <div className="progress-bar" style={{ width: `${Math.max(pct, 5)}%` }} />
          <span className="progress-text">{pct < 100 ? `上传 ${pct}%` : '服务端解析中…'}</span>
        </div>
      )}
      <p className="hint">
        支持 PDF / PPTX（幻灯片）/ DOCX 三种格式，单文件不超过 50MB；旧版 .ppt / .doc 请先「另存为」新格式；扫描版、纯图片内容暂不支持（未接入 OCR，不会谎报成功）
      </p>
      {error && <p className="error">⚠ {error}</p>}
      {current && (
        <p className="doc-info">
          ✅ {current.filename}（{FILE_TYPE_LABELS[current.file_type] ?? current.file_type}）· {current.unit_count} {current.unit_label}
          · {current.total_chars.toLocaleString()} 字符
          {current.course_id && current.course_id !== 'default' ? ` · 课程「${current.course_id}」` : ''}
          {current.sections?.length ? ` · ${current.sections.length} 个章节` : ''}
        </p>
      )}
    </section>
  )
}
