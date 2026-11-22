import { useState } from 'react'
import { ApiError, generateQuestions } from '../api'
import type { Cognitive, Difficulty, DocumentMeta, Question, QuestionType, QuestionsResult } from '../types'
import { COGNITIVE_LABELS, DIFFICULTY_LABELS, TYPE_LABELS } from '../types'
import ProviderNote from './ProviderNote'
import { LocChips } from './KeyPointsView'

const ALL_TYPES = Object.keys(TYPE_LABELS) as QuestionType[]
const OBJECTIVE: QuestionType[] = ['single', 'multi', 'judge']

export default function QuizView({ doc }: { doc: DocumentMeta }) {
  const [count, setCount] = useState(5)
  const [types, setTypes] = useState<QuestionType[]>(['single', 'judge'])
  const [difficulty, setDifficulty] = useState<Difficulty | ''>('')
  const [cognitive, setCognitive] = useState<Cognitive | ''>('')
  const [chapters, setChapters] = useState<string[]>([])
  const [res, setRes] = useState<QuestionsResult | null>(null)
  const [picked, setPicked] = useState<Record<number, string[]>>({})
  const [fillText, setFillText] = useState<Record<number, string>>({})
  const [revealed, setRevealed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const sections = (doc.sections ?? []).map((s) => s.title).filter(Boolean)

  async function run() {
    setBusy(true)
    setError(null)
    try {
      const out = await generateQuestions(doc.doc_id, {
        count,
        types,
        difficulty: difficulty || null,
        cognitive: cognitive || null,
        chapters,
      })
      setRes(out)
      setPicked({})
      setFillText({})
      setRevealed(false)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '生成失败，请重试')
    } finally {
      setBusy(false)
    }
  }

  function toggleType(t: QuestionType) {
    setTypes((prev) => (prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t]))
  }

  function toggleChapter(c: string) {
    setChapters((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]))
  }

  function pick(qi: number, label: string, multi: boolean) {
    setPicked((prev) => {
      const cur = prev[qi] ?? []
      const next = multi ? (cur.includes(label) ? cur.filter((l) => l !== label) : [...cur, label]) : [label]
      return { ...prev, [qi]: next }
    })
  }

  function isCorrect(q: Question, i: number): boolean | null {
    if (OBJECTIVE.includes(q.type)) {
      return [...(picked[i] ?? [])].sort().join() === [...q.answer].sort().join()
    }
    if (q.type === 'fill') {
      const t = (fillText[i] ?? '').trim()
      return !!t && (q.answers ?? []).some((a) => t.includes(a) || a.includes(t))
    }
    return null
  }

  const objective = res?.questions.filter((q) => OBJECTIVE.includes(q.type) || q.type === 'fill') ?? []
  const score = objective.filter((q, i) => isCorrect(q, res!.questions.indexOf(q)) === true).length

  return (
    <div>
      <div className="quiz-controls">
        <label>
          题数
          <input type="number" min={1} max={20} value={count} onChange={(e) => setCount(Number(e.target.value) || 1)} />
        </label>
        <label>
          难度
          <select value={difficulty} onChange={(e) => setDifficulty(e.target.value as Difficulty | '')}>
            <option value="">不限</option>
            {Object.entries(DIFFICULTY_LABELS).map(([v, l]) => (
              <option key={v} value={v}>{l}</option>
            ))}
          </select>
        </label>
        <label>
          认知层次
          <select value={cognitive} onChange={(e) => setCognitive(e.target.value as Cognitive | '')}>
            <option value="">不限</option>
            {Object.entries(COGNITIVE_LABELS).map(([v, l]) => (
              <option key={v} value={v}>{l}</option>
            ))}
          </select>
        </label>
        <button className="primary" onClick={run} disabled={busy || types.length === 0}>
          {busy ? '出题中…' : res ? '重新出题' : '生成模拟考试题'}
        </button>
      </div>
      <div className="type-group">
        {ALL_TYPES.map((t) => (
          <label key={t}>
            <input type="checkbox" checked={types.includes(t)} onChange={() => toggleType(t)} />
            {TYPE_LABELS[t]}
          </label>
        ))}
      </div>
      {sections.length > 0 && (
        <div className="chapter-picker">
          <span className="hint">章节范围：</span>
          {sections.map((s) => (
            <button key={s} type="button" className={`chip-toggle${chapters.includes(s) ? ' on' : ''}`} onClick={() => toggleChapter(s)}>
              {s}
            </button>
          ))}
          {chapters.length > 0 && <button type="button" className="link" onClick={() => setChapters([])}>清除</button>}
        </div>
      )}
      {error && <p className="error">⚠ {error}</p>}
      {res && <ProviderNote provider={res.provider} />}
      {res && (
        <p className="review-note">
          质量审核：检查 {res.review.checked} 题 · 通过 {res.review.passed} · 排除 {res.review.excluded} · 重生成 {res.review.regenerated} 题
          {res.excluded.length > 0 && `（${res.excluded.length} 道题未通过审核，已排除不出现在卷面）`}
          {res.review.rule_only_fallback && '（模型语义审查不可用，仅规则审查）'}
        </p>
      )}
      {res && (
        <ol className="quiz-list">
          {res.questions.map((q, i) => {
            const ok = isCorrect(q, i)
            const warnings = (q.quality?.issues ?? []).filter((x) => x.startsWith('warning:'))
            return (
              <li key={q.id ?? i} className="item">
                <p className="stem">
                  {i + 1}. [{TYPE_LABELS[q.type]}] {q.stem}
                  <span className="qbadges">
                    <span className="badge badge-diff">{DIFFICULTY_LABELS[q.difficulty]}</span>
                    <span className="badge badge-cog">{COGNITIVE_LABELS[q.cognitive]}层</span>
                  </span>
                </p>
                <p className="hint">知识点：{q.knowledge_point || '—'}</p>

                {q.options.length > 0 &&
                  q.options.map((o) => (
                    <label key={o.label} className="option">
                      <input
                        type={q.type === 'multi' ? 'checkbox' : 'radio'}
                        name={`q${i}`}
                        checked={(picked[i] ?? []).includes(o.label)}
                        onChange={() => pick(i, o.label, q.type === 'multi')}
                        disabled={revealed}
                      />
                      {o.label}. {o.text}
                      {revealed && (
                        <span className="opt-note">
                          {q.answer.includes(o.label)
                            ? '✔ 正确项'
                            : `✘ ${q.wrong_option_notes.find((n) => n.label === o.label)?.why_wrong ?? '干扰项'}`}
                        </span>
                      )}
                    </label>
                  ))}

                {q.type === 'fill' && !revealed && (
                  <input className="fill-input" placeholder="请填写答案" value={fillText[i] ?? ''} onChange={(e) => setFillText({ ...fillText, [i]: e.target.value })} />
                )}

                {(q.type === 'short' || q.type === 'comprehensive') && !revealed && (
                  <textarea className="short-input" rows={3} placeholder="写下你的作答（显示答案后对照参考答案与评分要点）" value={fillText[i] ?? ''} onChange={(e) => setFillText({ ...fillText, [i]: e.target.value })} />
                )}

                {revealed && (
                  <div className="answer-block">
                    {OBJECTIVE.includes(q.type) && (
                      <p className={ok ? 'result ok' : 'result bad'}>{ok ? '✔ 回答正确' : '✘ 回答错误'} · 答案：{q.answer.join('')}</p>
                    )}
                    {q.type === 'fill' && (
                      <p className={ok === null ? 'result' : ok ? 'result ok' : 'result bad'}>
                        可接受答案：{(q.answers ?? []).join(' / ')}
                      </p>
                    )}
                    {q.explanation && <p className="explain">解析：{q.explanation}</p>}
                    {q.reference_answer && <p className="explain">参考答案：{q.reference_answer}</p>}
                    {!!q.scoring_points?.length && (
                      <ul className="why">
                        {q.scoring_points.map((s, j) => (
                          <li key={j}>{s}</li>
                        ))}
                      </ul>
                    )}
                    {warnings.length > 0 && <p className="warn-text">⚠ {warnings.map((w) => w.replace(/^warning:\s*/, '')).join('；')}</p>}
                  </div>
                )}
                <LocChips loc={q.location} pages={q.pages} doc={doc} />
              </li>
            )
          })}
        </ol>
      )}
      {res && res.excluded.length > 0 && (
        <details className="excluded">
          <summary>被质量审核排除的题目（{res.excluded.length}）</summary>
          {res.excluded.map((q, i) => (
            <p key={i} className="hint">[{TYPE_LABELS[q.type]}] {q.stem.slice(0, 60)}… 原因：{(q.quality?.issues ?? []).filter(x => !x.startsWith('warning:')).join('；')}</p>
          ))}
        </details>
      )}
      {res && res.questions.length > 0 && (
        <div className="quiz-footer">
          <button onClick={() => setRevealed(!revealed)}>
            {revealed ? `客观题得分：${score}/${objective.length}，收起答案` : '提交并显示答案解析'}
          </button>
        </div>
      )}
    </div>
  )
}
