"""Render field/wire matrix; no provider, user graph, URL probe or credentials.

The actual Generator validator, builder and Broker JSON transport run against a
synthetic authenticated opener. Server functions are frozen from the inspected
checkout and execute as AST-only pure functions. Media URL resolution is a
fixture boundary: media decoding, provider quality and billing are not tested.
"""
from __future__ import annotations

import ast
import asyncio
from collections import Counter
from copy import deepcopy
import hashlib
import importlib.util
import itertools
import json
import math
from pathlib import Path
import re
import sys
import unittest
from unittest import mock

TESTS = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("render_options_routing", TESTS / "HMB_Seedance_Capability_Routing_Regression.py")
assert spec and spec.loader
route = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = route
spec.loader.exec_module(route)
base, t = route.base, route.t

SERVER_SOURCE = r'''def _seedance_resolution_contract(model):
    """Return the one resolution contract shared by schema, billing, and submit."""
    fast_model="fast" in str(model).lower()
    if str(model) == "doubao-seedance-2-5-260628":
        # Seedance 2.5: 720p is the safe default; 1080p is available as an
        # explicit 10-bit HEVC output option.  4K is not part of this contract.
        return {"choices": ("480p", "720p", "1080p"), "default": "720p", "encoding": {"1080p": "hevc-10bit"}}
    choices=("480p","720p") if fast_model else ("480p","720p","1080p","4k")
    return {"choices":choices,"default":"720p" if fast_model else "1080p"}

def _seedance_duration_contract(model, body=None):
    """Keep ordinary bounds and resolve the explicit video task's sentinel."""
    if str(model) == "doubao-seedance-2-5-260628":
        task=str((body or {}).get("omni_reference_task_type") or "").strip().lower()
        if task in ("edit","extend"):
            contract={"min":4,"max":30,"smart":True}
            if task=="edit":contract["smart_only"]=True
            return contract
        return {"min": 4, "max": 30, "smart": False}
    return {"min": 4, "max": 15, "smart": True}

def _seedance_duration_value(model, body):
    """Validate once without truncating fractional values to the -1 sentinel."""
    raw=body.get("duration_seconds")
    if raw is None:raw=body.get("duration",5)
    try:
        if isinstance(raw,bool):raise ValueError
        value=int(raw)
        if isinstance(raw,float) and (not math.isfinite(raw) or raw!=value):raise ValueError
        if isinstance(raw,str) and not re.fullmatch(r"[+-]?\d+",raw.strip()):raise ValueError
    except (TypeError,ValueError,OverflowError):
        raise ValueError("'duration_seconds'는 정수여야 합니다") from None
    contract=_seedance_duration_contract(model,body)
    if contract.get("smart_only") and value!=-1:
        raise ValueError("Seedance 2.5 영상 편집 길이는 -1이어야 합니다.")
    if contract["smart"] and value==-1:return value
    if not contract["min"]<=value<=contract["max"]:
        raise ValueError(f"{model} 길이는 {contract['min']}~{contract['max']}초여야 합니다.")
    return value

def _seedance_video_task_constraints(model, body):
    """Apply the same edit/extend input constraints before reservation and POST."""
    task=str(body.get("omni_reference_task_type") or "").strip().lower()
    if model=="doubao-seedance-2-5-260628" and task in ("edit","extend"):
        if not body.get("video_urls"):
            raise ValueError("영상 편집·연장 작업에는 참조 영상이 필요합니다.")
        if str(body.get("aspect_ratio") or body.get("ratio") or "adaptive")!="adaptive":
            raise ValueError("Seedance 2.5 영상 편집·연장 비율은 adaptive여야 합니다.")

def _seedance_resolution(model, body):
    contract=_seedance_resolution_contract(model);body=dict(body or {})
    resolution=str(body.get("quality") or body.get("resolution") or contract["default"]).lower()
    if resolution not in contract["choices"]:
        raise ValueError(f"{model} 해상도는 {', '.join(contract['choices'])}만 지원합니다.")
    return resolution,SEEDANCE_RESOLUTION_DIMENSIONS[resolution]

def _seedance_draft_stage(model, body):
    """Separate ordinary video, 480p preview, and linked 1080p final input."""
    body=dict(body or {})
    if any(name in body for name in ("draft_source_duration_seconds","draft_source_video_count")):
        raise ValueError("Draft 과금 원본 정보는 Broker가 결정합니다.")
    draft=body.get("draft",False)
    if type(draft) is not bool:raise ValueError("draft는 boolean이어야 합니다.")
    source=body.get("draft_job_id")
    if source is not None and (type(source) is not str or not source.strip() or len(source)>100):
        raise ValueError("draft_job_id는 Broker 작업 ID여야 합니다.")
    has_source=source is not None
    if draft and has_source:raise ValueError("Draft 생성과 Draft 완성본 생성을 한 요청에 섞을 수 없습니다.")
    if (draft or has_source) and model!="doubao-seedance-2-5-260628":
        raise ValueError("Draft 모드는 Seedance 2.5 전용입니다.")
    if not draft and not has_source:return None
    output_format=body.get("output_format","mp4")
    if type(output_format) is not str or output_format.strip().lower() not in ("mp4","mov"):
        raise ValueError("Draft 출력 형식은 mp4 또는 mov여야 합니다.")
    resolution,_=_seedance_resolution(model,body)
    if body.get("quality") not in (None,"") and body.get("resolution") not in (None,""):
        if str(body["quality"]).lower()!=str(body["resolution"]).lower():
            raise ValueError("quality와 resolution이 일치해야 합니다.")
    if draft:
        if resolution!="480p":raise ValueError("Seedance 2.5 Draft는 480p만 지원합니다.")
        return "preview"
    if body.get("quality") in (None,"") and body.get("resolution") in (None,""):
        raise ValueError("Draft 완성본은 1080p 해상도를 명시해야 합니다.")
    if resolution!="1080p":raise ValueError("Draft 완성본은 1080p만 지원합니다.")
    if any(name in body for name in SEEDANCE_DRAFT_INHERITED_FIELDS):
        raise ValueError("Draft 완성본에는 프롬프트·참조 미디어·길이·비율·오디오 등 재사용 설정을 다시 보내면 안 됩니다.")
    return "final"

def _seedance_draft_final_options(body):
    """Validate the settings that the provider permits on a Draft final."""
    optional={"output_format":"mp4"}
    if "output_format" in body:
        value=body["output_format"]
        if type(value) is not str or value.strip().lower() not in ("mp4","mov"):
            raise ValueError("Draft 출력 형식은 mp4 또는 mov여야 합니다.")
        optional["output_format"]=value.strip().lower()
    for name in ("watermark","return_last_frame"):
        if name in body:
            if type(body[name]) is not bool:raise ValueError(f"{name}은 boolean이어야 합니다.")
            optional[name]=body[name]
    for name,minimum,maximum in (("execution_expires_after",3600,259200),("priority",0,9)):
        if name in body:
            value=body[name]
            if type(value) is not int or not minimum<=value<=maximum:
                raise ValueError(f"{name}은 {minimum}~{maximum} 정수여야 합니다.")
            optional[name]=value
    return optional

def _official_default_schema(provider,model,media):
    if provider == VOLCENGINE_PROVIDER and model in SEEDANCE_MODEL_SET:
        resolution_contract=_seedance_resolution_contract(model)
        resolutions=list(resolution_contract["choices"])
        quality_default=resolution_contract["default"]
        reference_limits=(30,10,10) if model == "doubao-seedance-2-5-260628" else (9,3,3)
        schema={
            "prompt":{"type":"text","required":False},
            "input_mode":{"type":"select","choices":["Text Only","First/Last Frame","Multimodal References"],"default":"Multimodal References"},
            "first_frame":{"type":"file_list","artifact":"image","max":1},
            "last_frame":{"type":"file_list","artifact":"image","max":1,"required_with":"first_frame"},
            "image_urls":{"type":"file_list","artifact":"image","max":reference_limits[0]},
            "video_urls":{"type":"file_list","artifact":"video","max":reference_limits[1]},
            "audio_urls":{"type":"file_list","artifact":"audio","max":reference_limits[2]},
            "duration_seconds":{"type":"integer","min":_seedance_duration_contract(model)["min"],"max":_seedance_duration_contract(model)["max"],"default":5},
            "quality":{"type":"select","choices":resolutions,"default":quality_default},
            "aspect_ratio":{"type":"select","choices":["adaptive","21:9","16:9","4:3","1:1","3:4","9:16"],"default":"adaptive"},
            "generate_audio":{"type":"boolean","default":False},
            "watermark":{"type":"boolean","default":False},
            "return_last_frame":{"type":"boolean","default":False},
            "execution_expires_after":{"type":"integer","min":3600,"max":259200,"default":172800},
        }
        if model=="doubao-seedance-2-5-260628":
            schema["omni_reference_task_type"]={"type":"select","choices":["reference","edit","extend"],"default":"reference"}
            schema["output_format"]={"type":"select","choices":["mp4","mov"],"default":"mp4"}
            schema["draft"]={"type":"boolean","default":False}
            schema["draft_job_id"]={"type":"text","required":False}
        return schema
    return {"prompt":{"type":"text","required":True}}

def validate_model_request(item,payload):
    errors=[];schema=json.loads(item.get("input_schema_json") or "{}")
    draft_stage=None
    parsed_duration=None
    duration_contract=None
    if item.get("provider")==VOLCENGINE_PROVIDER and item.get("model") in SEEDANCE_MODEL_SET:
        try:draft_stage=_seedance_draft_stage(item.get("model"),payload)
        except ValueError as exc:errors.append(str(exc))
        duration_contract=_seedance_duration_contract(item.get("model"),payload)
        if draft_stage!="final":
            try:parsed_duration=_seedance_duration_value(item.get("model"),payload)
            except ValueError as exc:errors.append(str(exc))
            try:_seedance_video_task_constraints(item.get("model"),payload)
            except ValueError as exc:errors.append(str(exc))
    for raw_name,rule in schema.items():
        if not isinstance(rule,dict):continue
        name={"duration":"duration_seconds"}.get(raw_name,raw_name);value=payload.get(name)
        if name=="duration_seconds" and value is None:value=payload.get("duration")
        empty=value in (None,"") or value==[]
        if rule.get("required") and empty and not (draft_stage=="final" and name in SEEDANCE_DRAFT_INHERITED_FIELDS):
            errors.append(f"필수 입력 '{rule.get('label') or name}'이 비어 있습니다")
        dependency=rule.get("required_with")
        if not empty and dependency:
            dependency={"duration":"duration_seconds"}.get(str(dependency),str(dependency));other=payload.get(dependency)
            if other in (None,"") or other==[]:errors.append(f"'{name}'을 사용하려면 '{dependency}' 입력이 필요합니다")
        values=value if isinstance(value,list) else ([] if empty else [value])
        if rule.get("type")=="file" and len(values)>1:errors.append(f"'{name}'은 파일 1개만 받을 수 있습니다")
        if isinstance(rule.get("max"),int) and len(values)>rule["max"]:errors.append(f"'{name}'은 최대 {rule['max']}개까지 받을 수 있습니다")
        if rule.get("type")=="select" and not empty and value not in rule.get("choices",[]):errors.append(f"'{name}' 값이 허용 목록에 없습니다")
        smart_duration=(name=="duration_seconds" and item.get("provider")==VOLCENGINE_PROVIDER
                        and ((parsed_duration==-1 and duration_contract and duration_contract["smart"])
                             or (duration_contract is None and value==-1)))
        if not empty and isinstance(value,(int,float)) and not smart_duration:
            if rule.get("min") is not None and value<rule["min"]:errors.append(f"'{name}' 최소값은 {rule['min']}입니다")
            if rule.get("max") is not None and value>rule["max"]:errors.append(f"'{name}' 최대값은 {rule['max']}입니다")
        if rule.get("type") in ("integer","number") and not empty:
            try:numeric_value=float(value)
            except (TypeError,ValueError,OverflowError):
                if name!="duration_seconds" or duration_contract is None:errors.append(f"'{name}'은 숫자여야 합니다")
                continue
            if not smart_duration and rule.get("min") is not None and numeric_value<float(rule["min"]):errors.append(f"'{name}'은 {rule['min']} 이상이어야 합니다")
            if not smart_duration and rule.get("max") is not None and numeric_value>float(rule["max"]):errors.append(f"'{name}'은 {rule['max']} 이하여야 합니다")
    if item.get("provider")==VOLCENGINE_PROVIDER and item.get("model") in SEEDANCE_MODEL_SET:
        media_fields=("first_frame","last_frame","image_urls","video_urls","audio_urls")
        has_media=any(payload.get(name) not in (None,"",[]) for name in media_fields)
        if draft_stage!="final" and not str(payload.get("prompt") or "").strip() and not has_media:
            errors.append("프롬프트 또는 지원되는 참조 미디어가 필요합니다")
    return errors

def _volcengine_video_payload(model,body,*,draft_source=None):
    draft_stage=_seedance_draft_stage(model,body)
    if draft_stage=="final":
        provider_job_id=(draft_source or {}).get("provider_job_id") if isinstance(draft_source,dict) else None
        if not isinstance(provider_job_id,str) or not provider_job_id.strip():
            raise ValueError("Draft 완성본에는 검증된 Broker Draft 작업이 필요합니다.")
        return {"model":model,"content":[{"type":"draft_task","draft_task":{"id":provider_job_id}}],
                "resolution":"1080p",**_seedance_draft_final_options(body)}
    fast_model="fast" in model;resolution,_=_seedance_resolution(model,body)
    duration=_seedance_duration_value(model,body)
    _seedance_video_task_constraints(model,body)
    ratio=str(body.get("aspect_ratio") or body.get("ratio") or "adaptive")
    if ratio not in ("adaptive","21:9","16:9","4:3","1:1","3:4","9:16"):raise ValueError("지원하지 않는 영상 비율입니다.")
    images=list(body.get("image_urls") or []);videos=list(body.get("video_urls") or []);audio=list(body.get("audio_urls") or [])
    first=list(body.get("first_frame") or []);last=list(body.get("last_frame") or [])
    input_mode=str(body.get("input_mode") or ("First/Last Frame" if first or last else "Multimodal References" if images or videos or audio else "Text Only"))
    image_limit=30 if model=="doubao-seedance-2-5-260628" else 9
    video_limit=10 if model=="doubao-seedance-2-5-260628" else 3
    audio_limit=10 if model=="doubao-seedance-2-5-260628" else 3
    if len(images)>image_limit or len(videos)>video_limit or len(audio)>audio_limit:
        raise ValueError(f"Seedance 참조 제한은 이미지 {image_limit}개, 영상 {video_limit}개, 오디오 {audio_limit}개입니다.")
    if audio and not (images or videos):raise ValueError("참조 오디오는 참조 이미지 또는 영상과 함께 사용해야 합니다.")
    if first or last:
        if images or videos or audio:raise ValueError("첫/마지막 프레임 모드와 멀티모달 참조를 함께 사용할 수 없습니다.")
        if len(first)>1 or len(last)>1:raise ValueError("첫 프레임과 마지막 프레임은 각각 최대 1개입니다.")
    if input_mode=="Text Only" and (first or last or images or videos or audio):raise ValueError("Text Only 모드는 참조 미디어를 받을 수 없습니다.")
    if input_mode=="First/Last Frame" and (images or videos or audio):raise ValueError("First/Last Frame 모드는 멀티모달 참조 목록을 받을 수 없습니다.")
    if input_mode=="Multimodal References" and (first or last):raise ValueError("Multimodal References 모드는 first/last frame을 받을 수 없습니다.")
    omni_task=str(body.get("omni_reference_task_type") or "").strip().lower()
    output_format=str(body.get("output_format") or "mp4").strip().lower()
    return_last_frame=body.get("return_last_frame",False)
    if not isinstance(return_last_frame,bool):raise ValueError("return_last_frame은 boolean이어야 합니다.")
    if model=="doubao-seedance-2-5-260628":
        if omni_task and omni_task not in ("reference","edit","extend"):raise ValueError("지원하지 않는 Seedance 2.5 작업입니다.")
        if output_format not in ("mp4","mov"):raise ValueError("Seedance 2.5 출력 형식은 mp4 또는 mov여야 합니다.")
        if omni_task in ("edit","extend") and not videos:raise ValueError("영상 편집·연장 작업에는 참조 영상이 필요합니다.")
    elif omni_task or output_format!="mp4" or return_last_frame:
        raise ValueError("고급 작업·MOV·마지막 프레임 반환은 Seedance 2.5 전용입니다.")
    content=[];prompt=str(body.get("prompt") or "").strip()
    if prompt:content.append({"type":"text","text":prompt})
    for values,kind,role in ((first,"image","first_frame"),(last,"image","last_frame"),(images,"image","reference_image"),(videos,"video","reference_video"),(audio,"audio","reference_audio")):
        key=kind+"_url"
        for value in values:content.append({"type":key,key:{"url":_volcengine_media_url(value,kind)},"role":role})
    if not content:raise ValueError("프롬프트 또는 지원되는 참조 미디어가 필요합니다.")
    payload={"model":model,"content":content,"resolution":resolution,"ratio":ratio,"duration":duration,"generate_audio":bool(body.get("generate_audio",False)),"watermark":bool(body.get("watermark",False)),"return_last_frame":return_last_frame,"execution_expires_after":max(3600,min(259200,int(body.get("execution_expires_after") or 172800)))}
    if model=="doubao-seedance-2-5-260628":
        payload["output_format"]=output_format
        if omni_task:payload["omni_reference_task_type"]=omni_task
        if draft_stage=="preview":payload["draft"]=True
    if not fast_model:payload["priority"]=max(0,min(9,int(body.get("priority") or 0)))
    if len(json.dumps(payload,ensure_ascii=False).encode())>64*1024*1024:raise RequestBodyTooLarge("요청 본문은 64MiB 이하여야 합니다.")
    return payload'''
SERVER_FUNCTIONS = ('_seedance_resolution_contract', '_seedance_duration_contract', '_seedance_duration_value', '_seedance_video_task_constraints', '_seedance_resolution', '_seedance_draft_stage', '_seedance_draft_final_options', '_official_default_schema', 'validate_model_request', '_volcengine_video_payload')
SERVER_CONSTANTS = {'SEEDANCE_DRAFT_INHERITED_FIELDS': ('prompt', 'content', 'first_frame', 'last_frame', 'image_urls', 'video_urls', 'audio_urls', 'duration_seconds', 'duration', 'aspect_ratio', 'ratio', 'generate_audio', 'omni_reference_task_type', 'input_mode', 'seed'), 'SEEDANCE_RESOLUTION_DIMENSIONS': {'480p': (854, 480), '720p': (1280, 720), '1080p': (1920, 1080), '4k': (3840, 2160)}}
SERVER_HASHES = {'_seedance_resolution_contract': '5b8f03020e506717f900f1730ab251cfb43c8d05786433158e735c2b2705178c', '_seedance_duration_contract': '43be56eb8058389bc8194288057102398beb63ad83f8cb5b3108ab45cae49764', '_seedance_duration_value': 'f7a862f7bf5ec42582d8eb7fc7959b44dc381c51f7e7166ef56b5f961ab3a35c', '_seedance_video_task_constraints': 'ab463052524ffa4854497564e1903ffc5591e4499f98a16bc8238c1df9000bc1', '_seedance_resolution': 'ce4b78f64e4bd9a08782a7e19c07a2b0b8589315ec48eb067b34a2d7389f2a09', '_seedance_draft_stage': '96dcc1ff456f48043553376c007cfe540c388e0ebb9a0f8e56a0e9a5c0cb8a5a', '_seedance_draft_final_options': '7ee6c14cb8eed762be1fdd11340d5518a59d3789171b35c9a1ea165452322710', '_official_default_schema': '3d9d5da204c87056c07b1d8d7044ea6eeb90920e51f973e0706543922f90a70d', 'validate_model_request': '2f25401f253a98f95e6e9b830ace0513273ef95eb1fda9266469cf7feae6e5cb', '_volcengine_video_payload': '7ea415047f2f67f41660e275743c79246b1696a47497d42ddeea10446ac2b0e2'}
METRICS = Counter()


def server_namespace():
    namespace = {"json": json, "math": math, "re": re, "RequestBodyTooLarge": ValueError,
                 **SERVER_CONSTANTS, "SEEDANCE_MODEL_SET": set(t.BROKER_SUPPORTED_MODEL_IDS),
                 "VOLCENGINE_PROVIDER": "volcengine_ark"}
    # URLs are already neutral fixture references; this deliberately cannot
    # resolve DNS, read local media, fetch an asset, or reach a supplier.
    namespace["_volcengine_media_url"] = lambda value, kind: value
    exec(compile(ast.parse(SERVER_SOURCE), "<frozen-server-options>", "exec"), namespace)
    return namespace


SERVER = server_namespace()
MODELS = tuple(t.BROKER_SUPPORTED_MODEL_IDS)
METRIC_PATH = None


def values_for(model, task=t.TASK_TEXT_ONLY, **changes):
    values = base.params()
    values.update(model_id=model, task=task, input_mode=t.TASK_INPUT_MODES[task],
                  resolution=t.MODEL_DEFAULT_RESOLUTIONS[model], ratio="adaptive",
                  duration=-1 if task == t.TASK_VIDEO_EDITING else 4,
                  reference_images=[], video_references=[], reference_audio=[],
                  first_frame=None, last_frame=None, output_format="mov" if model == t.SEEDANCE_2_5_MODEL_ID else "mp4",
                  return_last_frame=False, draft_action=t.DRAFT_ACTION_OFF)
    if task == t.TASK_FIRST_LAST_FRAME:
        values["first_frame"] = "https://fixture.invalid/first.png"
    elif task == t.TASK_REFERENCE_TO_VIDEO:
        values["reference_images"] = ["https://fixture.invalid/reference.png"]
    elif task in (t.TASK_VIDEO_EDITING, t.TASK_VIDEO_EXTENSION):
        values["video_references"] = ["https://fixture.invalid/reference.mp4"]
    values.update(changes)
    return values


def prepared_wire(values):
    node = base.Node(values)
    node._prepare_media_reference = lambda kind, value: value
    payload = node._build_broker_payload(deepcopy(values))
    payload["client_request_id"] = "hmb-render-options-matrix"
    opener = route.RouteOpener()
    bridge = route.bridge_for(opener)
    bridge.generate_seedance(payload, timeout=1)
    wire = opener.posts[-1]["body"]
    schema = SERVER["_official_default_schema"]("volcengine_ark", values["model_id"], "video")
    errors = SERVER["validate_model_request"]({"provider": "volcengine_ark", "model": values["model_id"],
                                               "input_schema_json": json.dumps(schema)}, wire)
    if errors:
        raise AssertionError("Server schema rejected validated local wire: " + " / ".join(errors))
    provider = SERVER["_volcengine_video_payload"](values["model_id"], wire,
        draft_source={"provider_job_id": "offline-owned-draft"} if values.get("draft_action") == t.DRAFT_ACTION_FINAL else None)
    METRICS["valid_wire_and_server_payload_cases"] += 1
    return wire, provider


class RenderOptionMatrix(unittest.TestCase):
    def tearDown(self):
        while base.TEMPORARIES:
            base.TEMPORARIES.pop().cleanup()

    def test_frozen_server_functions_match_current_checkout_without_import(self):
        frozen = {node.name: node for node in ast.parse(SERVER_SOURCE).body}
        self.assertEqual(set(frozen), set(SERVER_FUNCTIONS))
        for name, node in frozen.items():
            self.assertEqual(route.function_hash(node), SERVER_HASHES[name])
        actual_path = Path("C:/API SERVER/app.py")
        if actual_path.is_file():
            actual = {node.name: node for node in ast.parse(actual_path.read_text(encoding="utf-8-sig")).body
                      if isinstance(node, ast.FunctionDef) and node.name in SERVER_FUNCTIONS}
            self.assertEqual(set(actual), set(frozen))
            for name, node in actual.items():
                self.assertEqual(route.function_hash(node), SERVER_HASHES[name], name)

    def test_model_task_resolution_ratio_matrix(self):
        for model, task, resolution, ratio in itertools.product(MODELS, t.TASK_STORAGE_CHOICES,
                ("480p", "720p", "1080p", "4k", "bad"), (*t.RATIOS, "bad")):
            values = values_for(model, task, resolution=resolution, ratio=ratio)
            allowed = (task in t.MODEL_TASK_CHOICES[model] and resolution in t.MODEL_RESOLUTIONS[model]
                       and ratio in t.RATIOS and not (model == t.SEEDANCE_2_5_MODEL_ID
                       and task in (t.TASK_FIRST_LAST_FRAME, t.TASK_VIDEO_EDITING, t.TASK_VIDEO_EXTENSION)
                       and ratio != "adaptive"))
            with self.subTest(model=model, task=task, resolution=resolution, ratio=ratio):
                if allowed:
                    wire, provider = prepared_wire(values)
                    self.assertEqual(provider["resolution"], resolution)
                    self.assertEqual(provider["ratio"], ratio)
                else:
                    with self.assertRaises(ValueError):
                        base.Node(values)._validate_parameters(deepcopy(values))
                    METRICS["invalid_model_task_resolution_ratio_cases"] += 1

    def test_all_integer_duration_choices_and_invalid_types(self):
        for model in MODELS:
            for task in t.MODEL_TASK_CHOICES[model]:
                for duration in (*range(-2, 33), True, 4.5, "4", None):
                    values = values_for(model, task, duration=duration)
                    allowed = (type(duration) is int and (duration == -1 if task == t.TASK_VIDEO_EDITING else
                        duration in t.DURATION_STORAGE_CHOICES if task == t.TASK_VIDEO_EXTENSION else
                        duration in t.MODEL_DURATION_CHOICES[model]))
                    with self.subTest(model=model, task=task, duration=duration):
                        if allowed:
                            wire, provider = prepared_wire(values)
                            self.assertEqual(provider["duration"], duration)
                        else:
                            with self.assertRaises(ValueError):
                                base.Node(values)._validate_parameters(deepcopy(values))
                            METRICS["invalid_duration_cases"] += 1

    def test_every_format_audio_watermark_last_frame_combination(self):
        for model in MODELS:
            for task in t.MODEL_TASK_CHOICES[model]:
                for output_format, last, audio, watermark in itertools.product(("mp4", "mov"), (False, True), (False, True), (False, True)):
                    values = values_for(model, task, output_format=output_format,
                        return_last_frame=last, generate_audio=audio, watermark=watermark)
                    with self.subTest(model=model, task=task, format=output_format, last=last, audio=audio, watermark=watermark):
                        wire, provider = prepared_wire(values)
                        self.assertIs(provider["generate_audio"], audio)
                        self.assertIs(provider["watermark"], watermark)
                        self.assertIs(provider["return_last_frame"], last if model == t.SEEDANCE_2_5_MODEL_ID else False)
                        if model == t.SEEDANCE_2_5_MODEL_ID:
                            self.assertEqual(provider["output_format"], output_format)
                        else:
                            self.assertNotIn("output_format", wire)
                            self.assertNotIn("return_last_frame", wire)

    def test_audio_only_is_rejected_before_auth_upload_or_submit_on_all_models(self):
        for model in MODELS:
            with self.subTest(model=model):
                values = values_for(model, t.TASK_REFERENCE_TO_VIDEO, reference_images=[],
                                    reference_audio=["https://fixture.invalid/reference.wav"])
                node = route.RoutingNode()
                node.values = values
                node._ensure_broker_connected = mock.AsyncMock(side_effect=AssertionError("auth before invalid-media rejection"))
                node._prepare_video_references_for_run = mock.Mock(side_effect=AssertionError("media upload before rejection"))
                with self.assertRaisesRegex(ValueError, "audio.*image or video"):
                    node._validate_parameters(deepcopy(values))
                with self.assertRaisesRegex(ValueError, "audio.*image or video"):
                    asyncio.run(node._process_generation_impl())
                node._ensure_broker_connected.assert_not_called()
                node._prepare_video_references_for_run.assert_not_called()
                self.assertEqual(node.transport.posts, [])
                METRICS["audio_only_pre_auth_pre_upload_no_submit_cases"] += 1

    def test_audio_with_either_visual_type_remains_supported(self):
        for model, kind in itertools.product(MODELS, ("image", "video")):
            values = values_for(model, t.TASK_REFERENCE_TO_VIDEO, reference_images=[],
                                reference_audio=["https://fixture.invalid/reference.wav"])
            values["reference_images" if kind == "image" else "video_references"] = [f"https://fixture.invalid/reference.{kind}"]
            wire, provider = prepared_wire(values)
            roles = [item.get("role") for item in provider["content"]]
            self.assertIn("reference_audio", roles)
            self.assertIn("reference_" + kind, roles)
            METRICS["visual_plus_audio_valid_cases"] += 1

    def test_draft_preview_and_sparse_final_contracts(self):
        for model, action in itertools.product(MODELS, (t.DRAFT_ACTION_PREVIEW, t.DRAFT_ACTION_FINAL)):
            for task in t.MODEL_TASK_CHOICES[model]:
                values = values_for(model, task, draft_action=action,
                    resolution="480p" if action == t.DRAFT_ACTION_PREVIEW else "1080p",
                    draft_job_id=base.JOB, return_last_frame=False, output_format="mov")
                with self.subTest(model=model, task=task, action=action):
                    if model != t.SEEDANCE_2_5_MODEL_ID:
                        with self.assertRaises(ValueError):
                            base.Node(values)._validate_parameters(deepcopy(values))
                    else:
                        wire, provider = prepared_wire(values)
                        self.assertEqual(SERVER["_seedance_draft_stage"](model, wire),
                                         "preview" if action == t.DRAFT_ACTION_PREVIEW else "final")
                        if action == t.DRAFT_ACTION_FINAL:
                            self.assertEqual(set(wire), {"provider", "model", "draft_job_id", "resolution",
                                "output_format", "project_id", "project_name", "client_request_id"})
                            self.assertEqual(provider["content"], [{"type": "draft_task", "draft_task": {"id": "offline-owned-draft"}}])

    def test_reference_count_boundaries_and_mutually_exclusive_roles(self):
        for model in MODELS:
            for field, limit in zip(("reference_images", "video_references", "reference_audio"), t.MODEL_REFERENCE_LIMITS[model]):
                for count in (limit, limit + 1):
                    values = values_for(model, t.TASK_REFERENCE_TO_VIDEO)
                    values[field] = [f"https://fixture.invalid/{field}-{index}" for index in range(count)]
                    with self.subTest(model=model, field=field, count=count):
                        if count == limit:
                            prepared_wire(values)
                            METRICS["reference_count_boundary_valid_cases"] += 1
                        else:
                            with self.assertRaisesRegex(ValueError, "at most"):
                                base.Node(values)._validate_parameters(deepcopy(values))
                            METRICS["reference_count_overflow_rejected_cases"] += 1
            invalid = (
                values_for(model, t.TASK_TEXT_ONLY, first_frame="https://fixture.invalid/frame.png"),
                values_for(model, t.TASK_TEXT_ONLY, reference_images=["https://fixture.invalid/image.png"]),
                values_for(model, t.TASK_FIRST_LAST_FRAME, first_frame=None, last_frame="https://fixture.invalid/last.png"),
                values_for(model, t.TASK_FIRST_LAST_FRAME, reference_images=["https://fixture.invalid/image.png"]),
                values_for(model, t.TASK_REFERENCE_TO_VIDEO, first_frame="https://fixture.invalid/frame.png"),
            )
            for values in invalid:
                with self.subTest(model=model, task=values["task"]), self.assertRaises(ValueError):
                    base.Node(values)._validate_parameters(deepcopy(values))
                METRICS["mixed_role_rejected_cases"] += 1
        for task in (t.TASK_VIDEO_EDITING, t.TASK_VIDEO_EXTENSION):
            values = values_for(t.SEEDANCE_2_5_MODEL_ID, task, video_references=[],
                                reference_images=["https://fixture.invalid/image.png"])
            with self.assertRaisesRegex(ValueError, "reference video"):
                base.Node(values)._validate_parameters(values)
            METRICS["missing_task_video_rejected_cases"] += 1

    def test_invalid_format_last_frame_and_draft_values(self):
        for field, candidates in (("output_format", ("avi", "", "unknown")),
                                   ("return_last_frame", ("False", 0, None))):
            for value in candidates:
                # Empty legacy format deliberately means default MP4.
                if field == "output_format" and value == "":
                    continue
                values = values_for(t.SEEDANCE_2_5_MODEL_ID, **{field: value})
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    base.Node(values)._validate_parameters(values)
                METRICS["invalid_format_or_frame_flag_rejected_cases"] += 1
        for action, resolution in ((t.DRAFT_ACTION_PREVIEW, "480p"), (t.DRAFT_ACTION_FINAL, "1080p")):
            for changes in ({"resolution": "720p"}, {"return_last_frame": True},
                            {"output_format": "avi"}, {"_hmb_draft_only": False, "_hmb_draft_supported": False}):
                values = values_for(t.SEEDANCE_2_5_MODEL_ID, draft_action=action,
                                    resolution=resolution, draft_job_id=base.JOB)
                values.update(changes)
                with self.subTest(action=action, changes=changes), self.assertRaises(ValueError):
                    base.Node(values)._validate_parameters(values)
                METRICS["invalid_draft_rejected_cases"] += 1

    def test_final_reuses_frozen_inputs_and_does_not_resend_current_optional_controls(self):
        values = values_for(t.SEEDANCE_2_5_MODEL_ID, t.TASK_REFERENCE_TO_VIDEO,
            draft_action=t.DRAFT_ACTION_FINAL, resolution="1080p", draft_job_id=base.JOB,
            prompt="current prompt must not replace the completed draft", generate_audio=True,
            watermark=True, execution_expires_after=3600, priority=0, return_last_frame=False)
        wire, provider = prepared_wire(values)
        for field in ("prompt", "image_urls", "video_urls", "audio_urls", "generate_audio",
                      "watermark", "return_last_frame", "execution_expires_after", "priority"):
            self.assertNotIn(field, wire)
        self.assertNotIn("watermark", provider)
        self.assertNotIn("return_last_frame", provider)
        # The server optionally accepts these overrides, but the dedicated
        # client Final is intentionally a sparse, source-linked action.
        optional = {**wire, "watermark": True, "return_last_frame": True,
                    "execution_expires_after": 3600, "priority": 0}
        explicit = SERVER["_volcengine_video_payload"](t.SEEDANCE_2_5_MODEL_ID, optional,
                    draft_source={"provider_job_id": "offline-owned-draft"})
        self.assertIs(explicit["watermark"], True)
        self.assertIs(explicit["return_last_frame"], True)
        METRICS["sparse_final_optional_control_cases"] += 1

    def test_expiry_priority_and_polling_boundaries(self):
        for model in MODELS:
            for name, candidates in (("execution_expires_after", (3599, 3600, 259200, 259201, True)),
                                     ("priority", (-1, 0, 9, 10, True)),
                                     ("poll_interval_seconds", (0, 1, 3601, True)),
                                     ("generation_timeout_seconds", (0, 1, 3600, True))):
                for value in candidates:
                    values = values_for(model, **{name: value})
                    allowed = type(value) is int
                    if name == "execution_expires_after": allowed = allowed and 3600 <= value <= 259200
                    elif name == "priority": allowed = allowed and 0 <= value <= 9 and (model == t.SEEDANCE_2_0_MODEL_ID or value == 0)
                    else: allowed = allowed and 0 < values["poll_interval_seconds"] <= values["generation_timeout_seconds"]
                    with self.subTest(model=model, field=name, value=value):
                        if allowed: prepared_wire(values)
                        else:
                            with self.assertRaises(ValueError): base.Node(values)._validate_parameters(deepcopy(values))


if __name__ == "__main__":
    t.AI_BROKER_SUBMISSION_MIN_INTERVAL_SECONDS = 0.0
    outcome = unittest.main(exit=False)
    print("HMB_RENDER_OPTIONS_METRICS " + json.dumps(dict(METRICS), sort_keys=True))
    raise SystemExit(0 if outcome.result.wasSuccessful() else 1)
