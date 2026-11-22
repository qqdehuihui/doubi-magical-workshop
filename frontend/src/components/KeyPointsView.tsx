import { useState } from 'react'
import { ApiError, getKeyPoints } from '../api'
import type { DocumentMeta, Grade, KeyPointsResult, ProviderInfo } from '../types'
import { EXAM_TYPE_ZH } from '../types'
import ProviderNote from './ProviderNote'

export function pageUnit(doc: DocumentMeta, p: number): string {
  if (doc.file_type === 'pptx') return `第${p}张幻灯片`
  if (doc.file_type === 'docx') return `表格${p}`
  return `第${p}页`
}

export function LocChips({ loc, pages, doc }: { loc?: string; pages?: number[]; doc: DocumentMeta }) {
  const chips: string[] = []
  if (loc) chips.push(loc)
  for (const p of pages ?? []) {
    const label = pageUnit(doc, p)
    if (label !== loc) chips.push(label)
  }
  if (!chips.length) return null
  const uniq = [...new Set(chips)]
  return (
    <span className="chips">
      {uniq.map((c) => (
        <span key={c} className="chip">
          {c}
        </span>
      ))}
    </span>
  )
}

function GradeBadge({ label, value }: { label: string; value: Grade }) {
  return <span className={`badge badge-${value === '高' ? 'hi' : value === '中' ? 'mid' : 'low'}`}>{label}{value}</span>
}

export default function KeyPointsView({ doc }: { doc: DocumentMeta }) {
  const [res, setRes] = useState<KeyPointsResult | null>(null)
  const [provider, setProvider] = useState<ProviderInfo | undefined>()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function run() {
    setBusy(true)
    setError(null)
    try {
      const out = await getKeyPoints(doc.doc_id)
      setRes(out)
      setProvider(out.provider)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '生成失败，请重试')
    } finally {
      setBusy(false)
    }
  }

  const hist = res?.historical_frequent

  return (
    <div>
      <button className="primary" onClick={run} disabled={busy}>
        {busy ? '分析中…（约需十几秒）' : res ? '重新分析重难点' : '开始重难点分析'}
      </button>
      {error && <p className="error">⚠ {error}</p>}
      {res && <ProviderNote provider={provider} />}

      {res && (
        <details className="legend">
          <summary>四个指标的含义（不可混同）</summary>
          <ul>
            {Object.entries(res.metrics_legend)
              .filter(([k]) => k !== 'warning')
              .map(([k, v]) => (
                <li key={k}>{v}</li>
              ))}
          </ul>
          <p className="legend-warning">{res.metrics_legend.warning}</p>
        </details>
      )}

      {res && (
        <div className="layers">
          <section className="layer">
            <h3>① 课程核心框架</h3>
            {res.course_framework.topic && <p className="stem">{res.course_framework.topic}</p>}
            <ol className="chapters">
              {res.course_framework.chapters.map((c, i) => (
                <li key={i}>
                  <b>{c.title}</b>
                  {c.summary && <p>{c.summary}</p>}
                  {c.location && <span className="chip">{c.location}</span>}
                </li>
              ))}
            </ol>
            {res.course_framework.relations.length > 0 && (
              <ul className="why">
                {res.course_framework.relations.map((r, i) => (
                  <li key={i}>
                    {r.from} → {r.to}：{r.relation}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="layer">
            <h3>② 核心知识点</h3>
            {res.core_knowledge.map((kp, i) => (
              <div key={i} className="item">
                <p className="stem">
                  {kp.item} <GradeBadge label="重要性" value={kp.importance} /> <GradeBadge label="课件强调" value={kp.emphasis} />
                  <span className="kind">{kp.kind}</span>
                </p>
                <p>{kp.content}</p>
                <LocChips loc={kp.location} pages={kp.pages} doc={doc} />
              </div>
            ))}
          </section>

          <section className="layer">
            <h3>③ 重难点解析</h3>
            {res.difficult_points.map((dp, i) => (
              <div key={i} className="item">
                <p className="stem">{dp.item}</p>
                <p>{dp.content}</p>
                {dp.why.length > 0 && (
                  <ul className="why">
                    {dp.why.map((w, j) => (
                      <li key={j}>{w}</li>
                    ))}
                  </ul>
                )}
                {dp.confusion?.with && (
                  <p className="confusion">
                    易混对比 · {dp.confusion.with}：{dp.confusion.difference}
                  </p>
                )}
                <LocChips loc={dp.location} pages={dp.pages} doc={doc} />
              </div>
            ))}
          </section>

          <section className="layer">
            <h3>④ 可能考查内容（基于课件强调度的推测，非统计结论）</h3>
            {res.exam_predictions.map((pr, i) => (
              <div key={i} className="item">
                <p className="stem">
                  {pr.item} <GradeBadge label="推测考查价值" value={pr.priority} />
                </p>
                {pr.basis.length > 0 && <p className="basis">依据：{pr.basis.join('；')}</p>}
                {pr.note && <p className="hint">{pr.note}</p>}
                <LocChips loc={pr.location} pages={pr.pages} doc={doc} />
              </div>
            ))}
          </section>

          <section className="layer">
            <h3>⑤ 历年高频考点（真实统计）</h3>
            {hist?.available ? (
              <>
                <p className="hint">
                  基于已导入的 {hist.paper_count} 份历年资料、{hist.question_total} 道题统计（来源：examdb_statistics）
                </p>
                <table className="stats-table">
                  <thead>
                    <tr>
                      <th>考点</th>
                      <th>出现次数</th>
                      <th>年份跨度</th>
                      <th>题型分布</th>
                      <th>合计分值</th>
                    </tr>
                  </thead>
                  <tbody>
                    {hist.items.map((it, i) => (
                      <tr key={i}>
                        <td>{it.point}</td>
                        <td>{it.count}</td>
                        <td>{it.span}</td>
                        <td>{Object.entries(it.types).map(([t, n]) => `${EXAM_TYPE_ZH[t] ?? t}×${n}`).join(' ')}</td>
                        <td>{it.score_total}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {hist.section_coverage && hist.section_coverage.length > 0 && (
                  <p className="hint">
                    章节覆盖：
                    {hist.section_coverage.map((sc) => `${sc.section}（${sc.matched_count}）`).join(' · ')}
                  </p>
                )}
              </>
            ) : (
              <p className="notice-box">{hist?.notice}</p>
            )}
          </section>
        </div>
      )}
    </div>
  )
}
