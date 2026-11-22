import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, deleteExam, getFrequentPoints, listExams, uploadExam } from '../api'
import type { ExamMeta, FrequentStats } from '../types'
import { EXAM_TYPE_ZH } from '../types'

const MATERIALS = ['试卷', '题库', '复习提纲']

export default function ExamBankView({ defaultCourse }: { defaultCourse?: string }) {
  const [course, setCourse] = useState(defaultCourse || '')
  const [material, setMaterial] = useState(MATERIALS[0])
  const [year, setYear] = useState('')
  const [busy, setBusy] = useState(false)
  const [pct, setPct] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [exams, setExams] = useState<ExamMeta[]>([])
  const [stats, setStats] = useState<FrequentStats | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const refresh = useCallback(async (c: string) => {
    if (!c.trim()) {
      setExams([])
      setStats(null)
      return
    }
    try {
      const [list, st] = await Promise.all([listExams(c.trim()), getFrequentPoints(c.trim())])
      setExams(list.exams)
      setStats(st)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '加载失败')
    }
  }, [])

  useEffect(() => {
    void refresh(course)
  }, [course, refresh])

  async function handleFile(file: File | undefined) {
    if (!file) return
    if (!course.trim()) {
      setError('请先填写课程标识，历年资料必须归属到课程')
      return
    }
    setBusy(true)
    setError(null)
    setNote(null)
    setPct(0)
    try {
      const out = await uploadExam(
        file,
        { course_id: course.trim(), material_type: material, year: year.trim() },
        setPct,
      )
      setNote(
        `已导入《${out.filename}》：识别 ${out.extracted_questions} 道题，年份 ${out.year}，类型「${out.material_type}」` +
          (out.note ? `。${out.note}` : ''),
      )
      await refresh(course)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '上传失败，请重试')
    } finally {
      setBusy(false)
      setPct(null)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  async function remove(id: string) {
    try {
      await deleteExam(id)
      await refresh(course)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '删除失败')
    }
  }

  return (
    <div className="exam-bank">
      <div className="exam-form">
        <input className="course-input" placeholder="课程标识（必填，与课件上传时一致）" value={course} onChange={(e) => setCourse(e.target.value)} />
        <select value={material} onChange={(e) => setMaterial(e.target.value)}>
          {MATERIALS.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
        <input className="year-input" placeholder="年份（可留空自动识别）" value={year} onChange={(e) => setYear(e.target.value)} inputMode="numeric" />
        <input ref={inputRef} type="file" accept=".pdf,.pptx,.docx" onChange={(e) => handleFile(e.target.files?.[0])} disabled={busy} />
        <button className="primary" onClick={() => handleFile(inputRef.current?.files?.[0])} disabled={busy}>
          {busy ? '导入中…' : '导入历年资料'}
        </button>
      </div>
      {busy && pct !== null && (
        <div className="progress">
          <div className="progress-bar" style={{ width: `${Math.max(pct, 5)}%` }} />
          <span className="progress-text">{pct < 100 ? `上传 ${pct}%` : '拆题统计中…'}</span>
        </div>
      )}
      <p className="hint">
        支持含文字的试卷 / 题库 / 复习提纲（PDF、DOCX、PPTX）。考点归一化由服务端统计，无法识别的年份、题型、分值将标记为「未知」，不做猜测。
      </p>
      {error && <p className="error">⚠ {error}</p>}
      {note && <p className="doc-info">✅ {note}</p>}

      {!course.trim() ? (
        <p className="notice-box">请输入课程标识，查看该课程已导入的历年资料与考频统计。</p>
      ) : (
        <>
          <h3>已导入资料（{exams.length}）</h3>
          {exams.length === 0 ? (
            <p className="notice-box">当前仅基于教师课件分析，尚未导入历年考试资料，无法统计真实考频。上传往年试卷后可生成历年高频考点分析。</p>
          ) : (
            <table className="stats-table">
              <thead>
                <tr>
                  <th>文件</th>
                  <th>类型</th>
                  <th>年份</th>
                  <th>题目数</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {exams.map((e) => (
                  <tr key={e.exam_doc_id}>
                    <td>{e.filename}</td>
                    <td>{e.material_type}</td>
                    <td>{e.year}</td>
                    <td>{e.question_count}</td>
                    <td>
                      <button type="button" className="link" onClick={() => remove(e.exam_doc_id)}>删除</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {stats && stats.available && (
            <>
              <h3>历年考点统计</h3>
              <p className="hint">
                {stats.paper_count} 份资料 · {stats.question_total} 道题 · 年份分布：
                {Object.entries(stats.by_year).map(([y, n]) => `${y}年${n}题`).join('，')} · 题型：
                {Object.entries(stats.by_type.types).map(([t, n]) => `${EXAM_TYPE_ZH[t] ?? t}×${n}`).join('，')}
              </p>
              <table className="stats-table">
                <thead>
                  <tr>
                    <th>考点</th>
                    <th>出现次数</th>
                    <th>年份</th>
                    <th>跨度</th>
                    <th>题型分布</th>
                    <th>合计分值</th>
                    <th>来源</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.points.map((p, i) => (
                    <tr key={i}>
                      <td>{p.point}</td>
                      <td>{p.count}</td>
                      <td>{p.years.join('、')}</td>
                      <td>{p.span}</td>
                      <td>{Object.entries(p.types).map(([t, n]) => `${EXAM_TYPE_ZH[t] ?? t}×${n}`).join(' ')}</td>
                      <td>{p.score_total}</td>
                      <td>{p.sources.join('、')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {stats.points.some((p) => p.question_samples.length > 0) && (
                <details className="excluded">
                  <summary>考点对应的真题示例</summary>
                  {stats.points.map((p, i) => (
                    <div key={i}>
                      <b>{p.point}</b>
                      {p.question_samples.map((s, j) => (
                        <p key={j} className="hint">「{s}」</p>
                      ))}
                    </div>
                  ))}
                </details>
              )}
            </>
          )}
        </>
      )}
    </div>
  )
}
