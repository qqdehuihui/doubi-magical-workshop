import type { ProviderInfo } from '../types'

export default function ProviderNote({ provider }: { provider?: ProviderInfo }) {
  if (!provider) return null
  if (provider.mock) {
    return <p className="provider-note mock">🧪 测试数据：由 Mock Provider 基于课件原文生成，非真实 AI 推理结果</p>
  }
  if (provider.name === 'rule') {
    return <p className="provider-note">{provider.disclaimer ?? '规则短路返回'}</p>
  }
  return (
    <p className="provider-note">
      模型：{provider.name}/{provider.model} · 耗时 {provider.elapsed_ms}ms
    </p>
  )
}
