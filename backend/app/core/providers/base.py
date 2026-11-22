from dataclasses import dataclass, field
from abc import ABC, abstractmethod


@dataclass
class GenerationRequest:
    task: str  # keypoints | questions | qa
    prompt: str
    system: str = ""
    evidence: list[dict] = field(default_factory=list)  # 检索到的分块（含页码）
    params: dict = field(default_factory=dict)


@dataclass
class GenerationResult:
    data: dict = field(default_factory=dict)
    text: str = ""
    provider: str = ""
    model: str = ""
    elapsed_ms: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    mock: bool = False

    def info(self) -> dict:
        info = {
            "name": self.provider,
            "model": self.model,
            "elapsed_ms": self.elapsed_ms,
            "mock": self.mock,
        }
        if self.mock:
            info["disclaimer"] = (
                "本结果由 Mock Provider 基于课件原文片段生成，属测试数据，"
                "不代表真实 AI 推理能力。"
            )
        return info


class BaseProvider(ABC):
    name: str = "base"

    @property
    def model_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def generate_text(self, req: GenerationRequest) -> GenerationResult:
        ...

    @abstractmethod
    def generate_json(self, req: GenerationRequest) -> GenerationResult:
        ...

    @abstractmethod
    def health_check(self) -> dict:
        ...

    def _make(self, **kwargs) -> GenerationResult:
        kwargs.setdefault("provider", self.name)
        kwargs.setdefault("model", self.model_name)
        return GenerationResult(**kwargs)
