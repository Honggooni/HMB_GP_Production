"""Local analysis transport using the approved production Broker and its scoped login."""
from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Any, Callable

_APPROVED_PRODUCTION_ORIGIN = "https://app.funnyflux.kr/GripTapeServer"
MODELS = ("gemini-4-carbon", "gemini-4-argon")
MAX_BODY_BYTES = 12 * 1024 * 1024
MAX_MEDIA_BYTES = 8 * 1024 * 1024
MIME_TYPES = frozenset(("image/png", "image/jpeg", "image/webp", "video/mp4", "video/quicktime",
    "audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp4", "audio/flac", "audio/ogg"))


class AnalysisBrokerError(ValueError):
    def __init__(self, code: str, message: str, *, receipt: dict | None = None):
        self.code = code
        self.receipt = receipt or {}
        super().__init__(message)


def production_origin() -> str:
    from _hmb_broker_config import DEFAULT_BROKER_BASE_URL

    if DEFAULT_BROKER_BASE_URL != _APPROVED_PRODUCTION_ORIGIN:
        raise AnalysisBrokerError("ANALYSIS_PRODUCTION_ORIGIN_REQUIRED", "승인된 운영 분석 서버 주소를 확인하세요.")
    return DEFAULT_BROKER_BASE_URL

def _live(is_live: Callable[[], bool]) -> None:
    if not is_live():
        raise AnalysisBrokerError("ANALYSIS_CANCELLED", "참조 분석을 취소했습니다.")


def request_payload(model: str, kind: str, prompt: str, attachments: list, context: dict, output_schema: dict) -> dict:
    if model not in MODELS or kind not in ("image", "video", "audio") or not isinstance(prompt, str) or not 0 < len(prompt) <= 32768:
        raise AnalysisBrokerError("ANALYSIS_REQUEST_INVALID", "분석 모델과 분석 지시를 확인하세요.")
    if not 0 < len(attachments) <= 96:
        raise AnalysisBrokerError("ANALYSIS_ATTACHMENT_LIMIT", "분석용 미디어 개수를 줄이세요.")
    rows, total = [], 0
    for label, blob, mime in attachments:
        if not isinstance(label, str) or len(label) > 1024 or not isinstance(blob, bytes) or not blob or mime not in MIME_TYPES:
            raise AnalysisBrokerError("ANALYSIS_ATTACHMENT_FORMAT", "분석용 미디어 형식을 확인하세요.")
        total += len(blob)
        if total > MAX_MEDIA_BYTES:
            raise AnalysisBrokerError("ANALYSIS_ATTACHMENT_LIMIT", "분석용 미디어가 너무 큽니다. 분석 구간을 줄이세요.")
        rows.append(dict(label=label, mime_type=mime, data_base64=base64.b64encode(blob).decode("ascii")))
    clean = {key: context[key] for key in ("channel_uuid", "shot_uuid", "source_sha256") if context.get(key)}
    if any(not isinstance(v, str) or len(v) > 128 for v in clean.values()) or (
            "source_sha256" in clean and not re.fullmatch(r"[0-9a-f]{64}", clean["source_sha256"])):
        raise AnalysisBrokerError("ANALYSIS_REQUEST_INVALID", "분석 소스와 샷 식별자를 확인하세요.")
    payload = dict(schema="hmb-reference-analysis-request-v1", model=model, kind=kind, prompt=prompt,
                   attachments=rows, context=clean, output_schema=output_schema)
    if len(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")) > MAX_BODY_BYTES:
        raise AnalysisBrokerError("ANALYSIS_ATTACHMENT_LIMIT", "분석 요청 크기를 줄이세요.")
    return payload


def validate_receipt(value: Any, model: str, kind: str, *, request_id: str = "") -> dict:
    if (not isinstance(value, dict) or value.get("schema") != "hmb-reference-analysis-response-v1"
            or not re.fullmatch(r"analysis-[0-9a-f]{32}", str(value.get("request_id", "")))
            or (request_id and value["request_id"] != request_id)
            or value.get("model") != model or value.get("kind") != kind or value.get("retryable") is not False
            or value.get("status") not in ("completed", "blocked", "failed", "submission_unknown", "submitting")):
        raise AnalysisBrokerError("ANALYSIS_RESULT_UNCONFIRMED", "분석 요청의 응답을 확인하지 못했습니다. 새 요청을 보내지 않습니다.")
    return value


class AnalysisClient:
    def __init__(self, model: str, kind: str, *, is_live: Callable[[], bool]):
        self.origin, self.model, self.kind, self.is_live = production_origin(), model, kind, is_live
        from HMBSeedanceGeneration import _HMBAIBrokerBridge
        self.bridge = _HMBAIBrokerBridge(server_url=self.origin)
        _live(is_live)
        self._request("GET", "/api/me", payload=None, timeout=5)
        with self.bridge._reference_principal_scope() as principal:
            if not principal:
                raise AnalysisBrokerError("ANALYSIS_AUTH_REQUIRED", "운영 Broker의 기존 사용자 로그인을 확인하세요.")
            self.principal = principal
        cap = self._request("GET", "/api/v1/analysis/capabilities", payload=None, timeout=5)
        self._same_owner()
        if (cap.get("schema") != "hmb-analysis-capabilities-v1" or cap.get("enabled") is not True
                or cap.get("automatic_retries") != 0
                or not any(isinstance(row, dict) and row.get("model_id") == model and row.get("enabled") is True
                           and kind in row.get("kinds", []) for row in cap.get("models", []))):
            raise AnalysisBrokerError("ANALYSIS_MODEL_UNAVAILABLE", "운영 서버에서 선택한 Gemini 분석 모델을 사용할 수 없습니다.")
        # Separate the native Cloud cache and each authenticated production owner.
        self.cache_scope = hashlib.sha256(json.dumps(["hmb-broker-analysis-v1", self.origin, principal]).encode()).hexdigest()

    def _same_owner(self) -> None:
        with self.bridge._reference_principal_scope() as principal:
            if principal != self.principal:
                raise AnalysisBrokerError("ANALYSIS_AUTH_CHANGED", "분석 중 사용자 인증이 변경되었습니다. 기존 요청을 확인하세요.")

    def _request(self, method: str, path: str, **kwargs) -> dict:
        _live(self.is_live)
        try:
            return self.bridge._request_json(method, path, **kwargs)
        except Exception as exc:
            code = getattr(exc, "status_code", None)
            if code == 401:
                raise AnalysisBrokerError("ANALYSIS_AUTH_REQUIRED", "운영 Broker의 기존 사용자 로그인을 확인하세요.") from None
            if method == "POST":
                raise AnalysisBrokerError("ANALYSIS_RESULT_UNCONFIRMED",
                    "운영 분석 요청의 결과를 확인하지 못했습니다. 자동으로 다시 제출하지 않습니다.") from None
            raise AnalysisBrokerError("ANALYSIS_SERVER_UNAVAILABLE",
                "운영 분석 서버의 상태를 확인하지 못했습니다.") from None

    def submit(self, prompt: str, attachments: list, context: dict, output_schema: dict,
               mark_submitted: Callable[[], None]) -> dict:
        payload = request_payload(self.model, self.kind, prompt, attachments, context, output_schema)
        key = "hmb-analysis-" + hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
        self._same_owner()
        _live(self.is_live)
        mark_submitted()
        # Exactly one create request. This path does not use the video retry helper.
        value = self._request("POST", "/api/v1/analysis", payload=payload, timeout=110,
                              submission=True, idempotency_key=key)
        self._same_owner()
        _live(self.is_live)
        value = validate_receipt(value, self.model, self.kind)
        status = value["status"]
        if status != "completed":
            messages = {"blocked": "공급자가 분석 요청을 차단했습니다.", "failed": "공급자가 분석 결과를 반환하지 않았습니다.",
                        "submission_unknown": "분석 제출 결과를 확인하지 못했습니다. 새 요청을 보내지 않습니다.",
                        "submitting": "기존 분석 요청이 진행 중입니다. 새 요청을 보내지 않습니다."}
            raise AnalysisBrokerError("ANALYSIS_" + status.upper(), messages[status], receipt=value)
        if not isinstance(value.get("output"), dict) or not any(value["output"].values()):
            raise AnalysisBrokerError("ANALYSIS_INVALID_RESULT", "분석 결과가 비어 있습니다.", receipt=value)
        return value

    def lookup(self, request_id: str) -> dict:
        if not re.fullmatch(r"analysis-[0-9a-f]{32}", request_id):
            raise AnalysisBrokerError("ANALYSIS_REQUEST_INVALID", "기존 분석 요청 ID를 확인하세요.")
        self._same_owner()
        value = self._request("GET", "/api/v1/analysis/" + request_id, payload=None, timeout=15)
        self._same_owner()
        return validate_receipt(value, self.model, self.kind, request_id=request_id)
