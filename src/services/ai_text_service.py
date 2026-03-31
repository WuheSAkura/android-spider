from __future__ import annotations

import json
import re
from typing import Any

from src.services.env_service import get_env
from src.utils.exceptions import ConfigError, DependencyError

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - 依赖检查由运行环境保证
    OpenAI = None


class TextCleaner:
    """从旧项目迁移的文本清洗器，当前只保留黑话研判所需能力。"""

    XIANYU_NOISE_PATTERNS = (
        r"(支持|接受|可以)?(当面|同城|线下)?交易",
        r"(不|拒绝)?刀(价)?",
        r"(包|免)?邮(费)?",
        r"(不)?议价",
        r"(诚心|真心|有意)?要(的)?私聊",
        r"(有意|想要|需要)?(的)?(联系|私聊|咨询)",
        r"(欢迎|随时)?(咨询|询问|了解)",
        r"(喜欢|中意)?(的)?(话)?(就|可以)?(下单|拍)",
        r"(谢谢|感谢)?(关注|支持|惠顾)",
        r"(限时|特价|优惠|打折|降价|清仓)",
        r"\d{4}年\d{1,2}月\d{1,2}日?(发布|上架)",
    )

    @staticmethod
    def clean_text(text: str, *, source_type: str) -> str:
        value = str(text or "")
        value = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", value)
        value = re.sub(r"[\ufeff\ufffe\uffff\u200b-\u200f\u202a-\u202e]", "", value)
        value = re.sub(r"\s+", " ", value).strip()

        if source_type == "xianyu":
            for pattern in TextCleaner.XIANYU_NOISE_PATTERNS:
                value = re.sub(pattern, "", value, flags=re.IGNORECASE)
            value = re.sub(r"\s+", " ", value).strip()

        return value


class AITextService:
    """黑话文本研判服务。

    Prompt 与 JSON 输出约定迁移自旧项目 `qwen_text_service.py`，
    但这里改为面向当前本地 SQLite 结构化记录输入。
    """

    def __init__(self) -> None:
        self._client: OpenAI | None = None

    def validate_configuration(self) -> None:
        if OpenAI is None:
            raise DependencyError("缺少 openai 依赖，请先安装 requirements.txt。")

        api_key = get_env("QWEN_API_KEY")
        if not api_key:
            raise ConfigError("未找到 QWEN_API_KEY，请在项目根目录 .env 中配置。")

    def analyze_jargon_records(
        self,
        *,
        records: list[dict[str, Any]],
        jargon_name: str,
        jargon_meaning: str,
        source_type: str,
        category_name: str | None = None,
        subcategory_name: str | None = None,
    ) -> dict[str, Any]:
        self.validate_configuration()
        if not records:
            return {"success": True, "results": []}

        client = self._get_client()
        normalized_records: list[dict[str, Any]] = []
        for record in records:
            record_id = record.get("record_id")
            if record_id is None:
                continue

            normalized_records.append(
                {
                    "record_id": int(record_id),
                    "title": str(record.get("title") or "").strip()[:120],
                    "content": TextCleaner.clean_text(
                        str(record.get("content") or ""),
                        source_type=source_type,
                    )[:700],
                    "metadata": str(record.get("metadata") or "").strip()[:240],
                }
            )

        if not normalized_records:
            return {"success": True, "results": []}

        prompt = f"""你是一个内容审核和黑话识别专家。

你需要根据“黑话名称”和“已经确认的内部代指含义”，判断每条记录是否在实际售卖、引流、展示或暗示相关商品/服务。

黑话名称：{jargon_name}
关联含义：{jargon_meaning}
一级分类：{category_name or '未提供'}
二级分类：{subcategory_name or '未提供'}
数据源类型：{source_type}

判定要求：
1. 不能只看是否出现黑话原词，要结合标题、正文、描述和上下文判断真实意图。
2. 如果记录明显在描述、售卖、暗示、引流与该黑话对应的商品/服务，判定为命中。
3. 如果只是无关提及、语义不足或明显不相关，判定为未命中。
4. 置信度范围为 0-100。
5. reason 必须简洁说明依据，20字以内。

请严格输出 JSON：
{{
  "results": [
    {{
      "record_id": 1,
      "is_match": true,
      "confidence": 92,
      "reason": "描述内容明确对应黑话含义"
    }}
  ]
}}
不要输出任何解释性文字。"""

        response = client.chat.completions.create(
            model=str(get_env("QWEN_MODEL", "qwen-plus")),
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(normalized_records, ensure_ascii=False, indent=2)},
            ],
            temperature=0.2,
            max_tokens=2000,
        )

        content = response.choices[0].message.content or ""
        parsed = self._parse_response(content)
        raw_results = parsed.get("results", [])
        result_map: dict[int, dict[str, Any]] = {}
        for item in raw_results:
            try:
                result_map[int(item.get("record_id"))] = item
            except (TypeError, ValueError):
                continue

        normalized_output: list[dict[str, Any]] = []
        for record in normalized_records:
            raw_item = result_map.get(record["record_id"], {})
            confidence = self._normalize_confidence(raw_item.get("confidence"))
            raw_match = raw_item.get("is_match", False)
            is_match = raw_match.strip().lower() in {"true", "1", "yes", "y"} if isinstance(raw_match, str) else bool(raw_match)
            normalized_output.append(
                {
                    "record_id": record["record_id"],
                    "is_match": is_match,
                    "confidence": confidence,
                    "reason": str(raw_item.get("reason") or "").strip()[:100],
                }
            )

        return {
            "success": True,
            "results": normalized_output,
            "raw_response": content,
            "model": str(get_env("QWEN_MODEL", "qwen-plus")),
        }

    def _get_client(self) -> OpenAI:
        if self._client is None:
            api_key = str(get_env("QWEN_API_KEY", ""))
            base_url = str(get_env("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"))
            self._client = OpenAI(api_key=api_key, base_url=base_url)
        return self._client

    @staticmethod
    def _parse_response(content: str) -> dict[str, Any]:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, flags=re.DOTALL)
            if match is not None:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    return {"results": []}
        return {"results": []}

    @staticmethod
    def _normalize_confidence(value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(100.0, number))


ai_text_service = AITextService()
