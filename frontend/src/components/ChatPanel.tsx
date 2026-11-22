import { useState } from 'react'
import { ApiError, sendChat } from '../api'
import type { ChatMessage, DocumentMeta, ProviderInfo } from '../types'
import ProviderNote from './ProviderNote'
import { pageUnit } from './KeyPointsView'

export default function ChatPanel({ doc }: { doc: DocumentMeta }) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [citations, setCitations] = useState<Record<number, { locs: string[]; pages: number[] }>>({})
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [provider, setProvider] = useState<ProviderInfo | undefined>()

  async function send() {
    const question = input.trim()
    if (!question || busy) return
    setBusy(true)
    setError(null)
    const history = [...messages]
    setMessages([...history, { role: 'user', content: question }])
    setInput('')
    try {
      const reply = await sendChat(doc.doc_id, question, history)
      setProvider(reply.provider)
      setMessages((prev) => {
        const idx = prev.length
        setCitations((c) => ({ ...c, [idx]: { locs: reply.locations ?? [], pages: reply.cited_pages ?? [] } }))
        return [...prev, { role: 'assistant', content: reply.answer }]
      })
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '回答失败，请重试')
      setMessages(history)
    } finally {
      setBusy(false)
    }
  }

  function chipsFor(c: { locs: string[]; pages: number[] }): string[] {
    const out = [...c.locs]
    for (const p of c.pages) {
      const label = pageUnit(doc, p)
      if (!out.includes(label)) out.push(label)
    }
    return out
  }

  return (
    <div className="chat">
      <div className="chat-log">
        {messages.length === 0 && <p className="hint">就《{doc.filename}》的内容提问，回答会标注原文来源位置</p>}
        {messages.map((m, i) => (
          <div key={i} className={m.role === 'user' ? 'msg user' : 'msg assistant'}>
            <span className="msg-role">{m.role === 'user' ? '我' : '助手'}</span>
            <div>{m.content}</div>
            {m.role === 'assistant' && citations[i] && chipsFor(citations[i]).length > 0 && (
              <span className="chips">
                {chipsFor(citations[i]).map((c) => (
                  <span key={c} className="chip">{c}</span>
                ))}
              </span>
            )}
          </div>
        ))}
        {busy && <p className="hint">思考中…</p>}
        {messages.length > 0 && <ProviderNote provider={provider} />}
      </div>
      {error && <p className="error">⚠ {error}</p>}
      <div className="chat-input">
        <input
          value={input}
          placeholder="例如：第三章的核心公式是什么？"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send()}
          disabled={busy}
        />
        <button className="primary" onClick={send} disabled={busy || !input.trim()}>
          发送
        </button>
      </div>
    </div>
  )
}
