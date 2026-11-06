"""程序说明：OpenAI 兼容在线模型，只解析合法行动并叙述已提交事实，失败时按契约回退。"""

from __future__ import annotations

import json
import logging
import re
import threading
import time

import httpx

from app.case_content import ACTIONS
from app.director import BEAT_TYPES, DIRECTOR_EFFECTS
from app.model import SimulatedModel, SimulationError
from app.narrative_context import (
    OUTCOME_LABELS,
    REPEAT_SIMILARITY_THRESHOLD,
    ngram_similarity,
)

logger = logging.getLogger("localhero.llm")
MAX_NARRATIVE_CHARS = 600


class ProviderRequestError(RuntimeError):
    """表示在线 Provider 请求失败，错误信息不得包含密钥。"""


class ProviderModel:
    """在线模型：意图失败回退本地匹配，叙事失败交由行动待重试。"""

    def __init__(
        self,
        config,
        fallback: SimulatedModel | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep=time.sleep,
    ):
        self.config = config
        self.fallback = fallback or SimulatedModel()
        self._transport = transport
        self._sleep = sleep
        self._stats_lock = threading.Lock()
        self._stats = {
            "requests": 0,
            "failures": 0,
            "fallbacks": 0,
            "total_ms": 0.0,
            "last_ms": 0.0,
        }

    def public_info(self) -> dict:
        """返回健康接口可公开的 Provider 信息。"""
        return self.config.public_info()

    def stats(self) -> dict:
        """返回调用次数、失败与回退统计；不包含请求内容或密钥。"""
        with self._stats_lock:
            return {key: round(value, 2) if isinstance(value, float) else value
                    for key, value in self._stats.items()}

    def _record_request(self, failed: bool, elapsed_ms: float) -> None:
        """记录一次完整 Chat Completions 调用的结果与耗时。"""
        with self._stats_lock:
            self._stats["requests"] += 1
            self._stats["last_ms"] = elapsed_ms
            self._stats["total_ms"] += elapsed_ms
            if failed:
                self._stats["failures"] += 1

    def _record_fallback(self) -> None:
        """记录一次因模型输出不可用而回到本地确定性逻辑。"""
        with self._stats_lock:
            self._stats["fallbacks"] += 1

    def parse_action(self, text: str, legal_actions: list[dict] | None = None) -> dict:
        """把自由输入映射为合法案件行动；失败时回退确定性解析。"""
        legal_actions = legal_actions or []
        if not legal_actions:
            return self.fallback.parse_action(text, legal_actions)
        try:
            content = self._chat(
                self._parse_messages(text, legal_actions), max_tokens=256, temperature=0.0
            )
            data = self._load_object(content)
            if data.get("kind") != "case_action":
                raise ProviderRequestError("未匹配固定行动")
            action_id = str(data.get("action_id") or "")
            action = next((item for item in legal_actions if item["id"] == action_id), None)
            if action is None:
                raise ProviderRequestError("返回行动不在合法目录")
            return {
                "kind": "case_action",
                "action_id": action["id"],
                "label": action["label"],
                "tendency": action["tendency"],
                "requires_roll": action["requires_roll"],
                "modifier": action["modifier"],
            }
        except Exception as exc:
            logger.info("在线意图解析回退：%s", self._safe_reason(exc))
            self._record_fallback()
            return self.fallback.parse_action(text, legal_actions)

    def propose_director(self, context: dict) -> dict | None:
        """只允许模型从白名单选择效果编号；任何失败都返回无提案。"""
        try:
            content = self._chat(
                self._director_messages(context), max_tokens=200, temperature=0.0
            )
            data = self._load_object(content)
            beat_type = str(data.get("beat_type") or "")
            effect_id = str(data.get("effect_id") or "")
            effect = DIRECTOR_EFFECTS.get(effect_id)
            if beat_type not in BEAT_TYPES or effect is None:
                raise ProviderRequestError("提案不在白名单")
            return {
                "beat_type": beat_type,
                "effect_id": effect_id,
                "target_action": context.get("当前行动编号"),
                "reason": str(data.get("reason") or "环境出现新的公开变化。"),
                "source": "provider",
            }
        except Exception as exc:
            logger.info("在线情节提案回退：%s", self._safe_reason(exc))
            self._record_fallback()
            return None

    def narrate(
        self,
        intent: dict,
        roll: dict | None,
        context: dict | None = None,
        previous_narratives: list[str] | None = None,
        action_content: dict | None = None,
    ) -> str:
        """只根据已提交意图、上下文与固定要点生成文字；重复时重试或回退。"""
        messages = self._narrate_messages(intent, roll, context, action_content=action_content)
        try:
            content = self._chat(messages, max_tokens=800, temperature=0.7)
        except Exception as exc:
            logger.warning("在线叙事失败：%s", self._safe_reason(exc))
            raise SimulationError("在线叙事暂时不可用，请稍后重试") from exc
        text = self._clean_text(content)
        if not self._usable_text(text):
            raise SimulationError("在线叙事返回不可用内容，请稍后重试")

        if not self._is_repetitive(text, previous_narratives):
            return text

        # 首次命中重复时只重试一次；仍失败则回到固定要点，避免无限调用。
        logger.info("在线叙事与近期内容高度相似，重试一次")
        retry_messages = self._narrate_messages(
            intent, roll, context, avoid=previous_narratives,
            action_content=action_content,
        )
        try:
            content = self._chat(retry_messages, max_tokens=800, temperature=0.8)
            retry_text = self._clean_text(content)
        except Exception as exc:
            logger.warning("在线叙事重试失败：%s", self._safe_reason(exc))
            return self._reference_text(intent, roll, action_content)

        if self._usable_text(retry_text) and not self._is_repetitive(
            retry_text, previous_narratives
        ):
            return retry_text
        logger.warning("在线叙事重试仍高度相似，回退固定要点")
        return self._reference_text(intent, roll, action_content)

    def _usable_text(self, text: str) -> bool:
        """检查文本非空、长度合规且不是 JSON 对象。"""
        return bool(text) and len(text) <= MAX_NARRATIVE_CHARS and not text.startswith("{")

    def _is_repetitive(self, text: str, previous_narratives: list[str] | None) -> bool:
        """与最近叙事做字符 n-gram 对比，超过阈值视为重复。"""
        for previous in previous_narratives or []:
            if previous and ngram_similarity(text, previous) >= REPEAT_SIMILARITY_THRESHOLD:
                return True
        return False

    def _chat(self, messages: list[dict], max_tokens: int, temperature: float) -> str:
        """串行调用 Chat Completions，超时与重试有界，日志脱敏。"""
        url = self.config.base_url + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        payload = {
            "model": self.config.model_name,
            "messages": messages,
            "max_tokens": min(max_tokens, self.config.max_output_tokens),
            "temperature": temperature,
        }
        attempts = self.config.max_retries + 1
        last_error: Exception | None = None
        started = time.time()
        succeeded = False

        try:
            with httpx.Client(
                timeout=self.config.timeout_seconds, transport=self._transport
            ) as client:
                for attempt in range(attempts):
                    try:
                        response = client.post(url, headers=headers, json=payload)
                    except httpx.TimeoutException:
                        last_error = ProviderRequestError("请求超时")
                        logger.info("Provider 超时：attempt=%s/%s", attempt + 1, attempts)
                        self._sleep_before_retry(attempt, attempts)
                        continue
                    except httpx.HTTPError as exc:
                        last_error = ProviderRequestError(f"网络错误：{type(exc).__name__}")
                        logger.info("Provider 网络错误：attempt=%s/%s", attempt + 1, attempts)
                        self._sleep_before_retry(attempt, attempts)
                        continue

                    status = response.status_code
                    if status == 429 or status >= 500:
                        last_error = ProviderRequestError(f"HTTP {status}")
                        logger.info("Provider 暂不可用：status=%s attempt=%s/%s", status, attempt + 1, attempts)
                        self._sleep_before_retry(attempt, attempts)
                        continue
                    if status >= 400:
                        raise ProviderRequestError(f"HTTP {status}")

                    try:
                        data = response.json()
                        content = data["choices"][0]["message"]["content"] or ""
                    except (ValueError, KeyError, IndexError, TypeError) as exc:
                        raise ProviderRequestError("响应结构不合法") from exc

                    usage = data.get("usage") or {}
                    elapsed_ms = (time.time() - started) * 1000
                    logger.info(
                        "Provider 调用成功 provider=%s model=%s status=%s elapsed=%.2fs "
                        "prompt_tokens=%s completion_tokens=%s",
                        self.config.provider_name,
                        self.config.model_name,
                        status,
                        time.time() - started,
                        usage.get("prompt_tokens"),
                        usage.get("completion_tokens"),
                    )
                    self._record_request(False, elapsed_ms)
                    succeeded = True
                    return content

            raise last_error or ProviderRequestError("请求失败")
        finally:
            # 任何未走到成功记录的退出路径都计为一次最终失败。
            if not succeeded:
                self._record_request(True, (time.time() - started) * 1000)


    def _sleep_before_retry(self, attempt: int, attempts: int) -> None:
        """仅在仍有下次尝试时短暂退避。"""
        if attempt + 1 < attempts:
            self._sleep(min(2.0, 0.5 * (attempt + 1)))

    def _parse_messages(self, text: str, legal_actions: list[dict]) -> list[dict]:
        """构造只含玩家输入与合法行动目录的解析提示。"""
        catalog = "\n".join(
            f"- {item['id']} | {item['label']} | 别名：{'、'.join(item.get('aliases') or []) or '无'}"
            for item in legal_actions
        )
        system = (
            "你是《灰区事务所》的行动解析器，只把玩家输入归类到当前地点的合法行动。\n"
            "规则：只能选择列表中的行动；不得发明行动、地点或结果；匹配不到时输出 no_match。\n"
            '只输出 JSON：{"kind":"case_action","action_id":"行动编号"} 或 {"kind":"no_match"}。'
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": f"合法行动：\n{catalog}\n\n玩家输入：{text}"},
        ]

    def _director_messages(self, context: dict) -> list[dict]:
        """构造只含公开白名单的情节提案提示。"""
        effects = "\n".join(
            f"- {item['effect_id']} | {item['text']}"
            for item in (context.get("可选效果") or [])
        )
        system = (
            "你是《灰区事务所》的情节导演，只能在固定案件框架内提出一条环境复杂化节拍。\n"
            "规则：只能从“可选效果”中选择 effect_id；不得新增人物、地点、线索、结局、数值、"
            "时间或判定；reason 不超过三十字，不得包含数字、人物名、地点名、线索或内部术语。\n"
            '只输出 JSON：{"beat_type":"environment_complication","effect_id":"效果编号",'
            '"reason":"简短理由"}。'
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": f"可选效果：\n{effects}\n\n当前行动：{context.get('当前行动')}"},
        ]

    def _narrate_messages(
        self,
        intent: dict,
        roll: dict | None,
        context: dict | None = None,
        avoid: list[str] | None = None,
        action_content: dict | None = None,
    ) -> list[dict]:
        """构造只含已提交事实、白名单上下文与固定要点的叙事提示。"""
        reference = self._reference_text(intent, roll, action_content)
        system = (
            "你是《灰区事务所》的叙事者，把已经提交的行动与判定写成 2—4 句中文。\n"
            "事实规则：\n"
            "1. “固定要点”是不可改变的事实边界，不是待复述的原文；不得照抄其中整句，也不得只做同义替换。\n"
            "2. 不得新增具名人物、新地点、新物品、新线索、新数值、新时间或新的判定结果。\n"
            "3. 不得替玩家做决定，不得描述未提交的后续事件，不得解释规则或复述玩家输入。\n"
            "4. 可以补充环境光线、声音、气味、温度、材质、身体感受和动作节奏等感官细节，"
            "但这些细节不得改变或暗示事实之外的结果。\n"
            "5. 不输出标题、列表、JSON、代码块或说明。\n"
            "6. 附带的“叙事上下文”只含已提交事实与玩家已知信息；只能用于保持连贯，"
            "不得据此推断隐藏真相、未公开线索或内部评分。\n"
            "7. 若附带“避免重复的近期叙事”，不得复用其中的措辞和句式。\n"
            "8. 人物口吻只约束动作、神态和已提交回应，不得新增台词、决定或人物关系。\n"
            "语气冷峻、具体、克制；优先写可感知的细节，不用空泛总结收尾。"
        )
        outcome = (roll or {}).get("outcome", "no_roll")
        fact = {
            "行动": intent.get("label") or intent.get("kind"),
            "倾向": intent.get("tendency"),
            "判定结果": OUTCOME_LABELS.get(outcome, outcome),
            "骰点合计": (roll or {}).get("total"),
            "固定要点（事实边界，不可照抄）": reference,
        }
        if context:
            fact["叙事上下文"] = context
        if avoid:
            fact["避免重复的近期叙事"] = list(avoid)[-2:]
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(fact, ensure_ascii=False)},
        ]

    def _reference_text(
        self,
        intent: dict,
        roll: dict | None,
        action_content: dict | None = None,
    ) -> str:
        """从固定案件内容读取结局要点，作为不可越界的事实边界。"""
        if intent.get("kind") != "case_action":
            return f"场景行动：{intent.get('label') or intent.get('kind')}"
        action = action_content or next(
            (item for item in ACTIONS if item["id"] == intent.get("action_id")), None
        )
        if action is None:
            return f"固定行动：{intent.get('label') or intent.get('action_id')}"
        narratives = action.get("narratives") or {}
        outcome = (roll or {}).get("outcome")
        return narratives.get(outcome) or next(iter(narratives.values()), "无额外结果")

    def _load_object(self, content: str) -> dict:
        """从可能带围栏的返回中提取第一个 JSON 对象。"""
        text = self._strip_fence(content)
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ProviderRequestError("返回内容不是 JSON")
        try:
            data = json.loads(text[start : end + 1])
        except ValueError as exc:
            raise ProviderRequestError("返回内容不是合法 JSON") from exc
        if not isinstance(data, dict):
            raise ProviderRequestError("返回内容不是 JSON 对象")
        return data

    def _clean_text(self, content: str) -> str:
        """去掉代码块围栏、首尾引号并压缩空白。"""
        text = self._strip_fence(content)
        if len(text) >= 2 and text[0] in {'"', "“"} and text[-1] in {'"', "”"}:
            text = text[1:-1]
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _strip_fence(content: str) -> str:
        """移除 Markdown 代码块围栏。"""
        text = (content or "").strip()
        if text.startswith("```"):
            lines = text.splitlines()
            lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        return text

    def _safe_reason(self, exc: Exception) -> str:
        """生成不含密钥的失败原因。"""
        message = f"{type(exc).__name__}: {exc}"
        if self.config.api_key:
            message = message.replace(self.config.api_key, "***")
        return message[:200]
