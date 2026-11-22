export type FileType = 'pdf' | 'pptx' | 'docx'

export interface Section {
  title: string
  start_page?: number
  end_page?: number
  slide?: number
  path?: string
}

export interface PageExcerpt {
  no: number
  text: string
}

export interface DocumentMeta {
  doc_id: string
  filename: string
  file_type: FileType
  page_count: number
  unit_count: number
  unit_label: string
  total_chars: number
  course_id?: string
  sections?: Section[]
  pages?: PageExcerpt[]
  created_at?: string
}

export interface ProviderInfo {
  name: string
  model: string
  elapsed_ms: number
  mock: boolean
  disclaimer?: string
}

export type Grade = '高' | '中' | '低'

export interface ChapterNode {
  title: string
  location: string
  summary: string
}

export interface CoreKnowledge {
  item: string
  kind: string
  content: string
  location: string
  importance: Grade
  emphasis: Grade
  pages: number[]
}

export interface DifficultPoint {
  item: string
  content: string
  why: string[]
  location: string
  pages: number[]
  confusion?: { with: string; difference: string } | null
}

export interface ExamPrediction {
  item: string
  priority: Grade
  basis: string[]
  location: string
  pages: number[]
  emphasis: Grade
  note?: string
}

export interface HistoryItem {
  point: string
  count: number
  years: string[]
  types: Record<string, number>
  score_total: number | '未知'
  span: string
  sources: string[]
  question_samples: string[]
}

export interface SectionCoverage {
  section: string
  matched_points: string[]
  matched_count: number
}

export interface HistoricalFrequent {
  available: boolean
  notice: string | null
  items: HistoryItem[]
  paper_count: number
  question_total: number
  by_year: Record<string, number>
  by_type: { types: Record<string, number>; labels: Record<string, string> }
  section_coverage: SectionCoverage[] | null
  source: 'examdb_statistics' | null
}

export interface KeyPointsResult {
  schema: string
  course_framework: {
    topic: string
    chapters: ChapterNode[]
    relations: { from: string; to: string; relation: string }[]
  }
  core_knowledge: CoreKnowledge[]
  difficult_points: DifficultPoint[]
  exam_predictions: ExamPrediction[]
  historical_frequent: HistoricalFrequent
  metrics_legend: Record<string, string>
  provider: ProviderInfo
  evidence_chunks: number
}

export type QuestionType = 'single' | 'multi' | 'judge' | 'fill' | 'short' | 'comprehensive'
export type Difficulty = 'basic' | 'medium' | 'hard' | 'challenge'
export type Cognitive = 'remember' | 'understand' | 'apply' | 'analyze' | 'evaluate' | 'create'

export interface QuestionOption {
  label: string
  text: string
}

export interface WrongNote {
  label: string
  why_wrong: string
}

export interface QuestionQuality {
  status: 'passed' | 'passed_with_warnings' | 'excluded'
  issues: string[]
}

export interface Question {
  id: number
  type: QuestionType
  stem: string
  options: QuestionOption[]
  answer: string[]
  explanation: string
  wrong_option_notes: WrongNote[]
  knowledge_point: string
  location: string
  pages: number[]
  difficulty: Difficulty
  cognitive: Cognitive
  answers?: string[]
  reference_answer?: string
  scoring_points?: string[]
  quality: QuestionQuality
}

export interface QuestionsResult {
  questions: Question[]
  excluded: Question[]
  review: {
    checked: number
    passed: number
    excluded: number
    regenerated: number
    audit_provider: ProviderInfo | null
    rule_only_fallback: boolean
  }
  params: {
    count: number
    types: QuestionType[]
    difficulty: Difficulty | null
    cognitive: Cognitive | null
    chapters: string[]
  }
  provider: ProviderInfo
  evidence_chunks: number
}

export interface ExamUploadResult {
  exam_doc_id: string
  filename: string
  file_type: FileType
  course_id: string
  material_type: string
  year: number | '未知'
  extracted_questions: number
  note: string | null
}

export interface ExamMeta {
  exam_doc_id: string
  filename: string
  file_type?: FileType
  course_id: string
  material_type: string
  year: number | '未知'
  question_count: number
}

export interface FrequentStats {
  available: boolean
  course_id: string
  papers: { exam_doc_id: string; filename: string; year: number | '未知'; material_type: string; question_count: number }[]
  paper_count: number
  question_total: number
  by_year: Record<string, number>
  by_type: { types: Record<string, number>; labels: Record<string, string> }
  points: HistoryItem[]
  section_coverage: SectionCoverage[] | null
  notice: string | null
}

export interface ChatReply {
  answer: string
  cited_pages: number[]
  locations: string[]
  insufficient_evidence?: boolean
  provider: ProviderInfo
  evidence_chunks: number
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export const TYPE_LABELS: Record<QuestionType, string> = {
  single: '单选',
  multi: '多选',
  judge: '判断',
  fill: '填空',
  short: '简答',
  comprehensive: '综合应用',
}

// 考试资料库统计中的题型代码 → 中文（与后端 _QTYPE_LABEL 对齐；unknown=未识别题型）
export const EXAM_TYPE_ZH: Record<string, string> = {
  single: '单选', multi: '多选', judge: '判断', fill: '填空', short: '简答', comprehensive: '综合', unknown: '未标注',
}

export const DIFFICULTY_LABELS: Record<Difficulty, string> = {
  basic: '基础',
  medium: '中等',
  hard: '较难',
  challenge: '挑战',
}

export const COGNITIVE_LABELS: Record<Cognitive, string> = {
  remember: '记忆',
  understand: '理解',
  apply: '应用',
  analyze: '分析',
  evaluate: '评价',
  create: '创造',
}

export const FILE_TYPE_LABELS: Record<FileType, string> = {
  pdf: 'PDF',
  pptx: 'PPTX 课件',
  docx: 'Word 文档',
}
