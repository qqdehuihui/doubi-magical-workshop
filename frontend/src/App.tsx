import { useState } from 'react'
import type { DocumentMeta } from './types'
import UploadPanel from './components/UploadPanel'
import KeyPointsView from './components/KeyPointsView'
import QuizView from './components/QuizView'
import ChatPanel from './components/ChatPanel'
import ExamBankView from './components/ExamBankView'

const TABS = [
  { key: 'keypoints', label: '重难点分析' },
  { key: 'quiz', label: '模拟考试' },
  { key: 'chat', label: '课件问答' },
  { key: 'exams', label: '历年资料库' },
] as const

type TabKey = (typeof TABS)[number]['key']

export default function App() {
  const [doc, setDoc] = useState<DocumentMeta | null>(null)
  const [tab, setTab] = useState<TabKey>('keypoints')

  return (
    <div className="app">
      <header className="header">
        <h1>AI 学习助手</h1>
        <p className="subtitle">上传 PDF / PPTX / Word 课件：五层重难点分析、六题型模拟考试、基于原文来源的问答，并可导入历年试卷统计真实考频</p>
      </header>

      <UploadPanel onUploaded={setDoc} current={doc} />

      <section className="workspace">
        <nav className="tabs">
          {TABS.map((t) => (
            <button
              key={t.key}
              className={tab === t.key ? 'tab active' : 'tab'}
              onClick={() => setTab(t.key)}
              disabled={t.key !== 'exams' && !doc}
              title={t.key !== 'exams' && !doc ? '请先上传课件' : undefined}
            >
              {t.label}
            </button>
          ))}
        </nav>
        <div className="tab-panel">
          {tab === 'exams' && <ExamBankView defaultCourse={doc?.course_id !== 'default' ? doc?.course_id : undefined} />}
          {tab === 'keypoints' && doc && <KeyPointsView doc={doc} />}
          {tab === 'quiz' && doc && <QuizView doc={doc} />}
          {tab === 'chat' && doc && <ChatPanel doc={doc} />}
        </div>
      </section>
    </div>
  )
}
