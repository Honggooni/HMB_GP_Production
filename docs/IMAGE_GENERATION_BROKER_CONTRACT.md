# HMB Image Generation: 개인용 통합 이미지 생성 계약

팀 v0.8.23 / 로컬 v0.8.24 대상의 클라이언트·Broker 계약이다. 통합 이미지 생성기, 모델별 옵션, 참조 자동 축소와 동일 Task 복구를 포함한다. 이 문서는 계약과 무과금 회귀 검사의 범위를 설명하며 운영 배포·공급자 키 준비·실제 모델 생성 성공을 증명하지 않는다.

## 사용자 동작

- 별도 `HMB Image Generation` 노드에서 **이미지 모델만 선택**한다. 오프라인 입력 안내는 Google Nano Banana Pro (`google/gemini-3-pro-image`)와 Nano Banana 2 (`google/gemini-3.1-flash-image`)를 제공한다. 실제 사용 가능 모델·옵션·자격증명은 서버가 알린다. 공급자 입력란이나 공급자별 전용 노드는 만들지 않는다.
- 텍스트 생성 / 참조 이미지 편집, 비율·이미지 크기·지원 출력 포맷을 선택한다. 입력 프롬프트를 그대로 제출하며 HMB Agent를 실행하지 않는다.
- 결과는 개인 로컬 파일로 저장하고 기본 이미지 미리보기와 `IMAGE_OUT`으로 제공한다. `HMBImageAssetLibrary.IMAGE_IMPORT_IN` 등 일반 이미지 입력에 연결할 수 있다.
- 프로젝트·샷 선택, 자동 어셋 등록, 작업관리 웹 게시가 없다. 기존 Seedance 영상의 프로젝트 필수 규칙은 바꾸지 않는다.
- 동일 Broker 주소와 보호된 사용자 로그인 세션을 사용한다. 사용자별 공급자 API 키 입력란·키 파일·키를 담은 워크플로는 만들지 않는다.

## 서버와 클라이언트의 준비 상태

이미지 생성은 개인용 이미지 adapter와 모델 registry를 사용한다. 초기 선택 프로필은 Nano Banana Pro와 Nano Banana 2이며, 모델별 고급 옵션과 출력 크기는 현재 서버가 광고한 capability를 따른다. 실제 모델 목록·`enabled`·`credential_ready`를 확인한 뒤 제출하며 오프라인 프로필이나 예시만으로 서버 지원을 간주하지 않는다. 클라이언트 패키지 검증, 서버 기능 활성화와 실제 공급자 응답 검증은 각각 구분한다.

## 기존 v1 capability와 호환 확장

인증은 기존 Bearer 세션이며 게이트웨이 경로 접두사를 유지한다. 아래 이름·필드는 서버와 클라이언트가 함께 구현할 고정 계약이다.

`GET /api/v1/image-generation/capabilities`

```json
{
  "schema": "hmb-image-generation-capabilities-v1",
  "version": 1,
  "enabled": true,
  "persistence_scope": "personal_local",
  "client_request_lookup": true,
  "max_request_bytes": 20000000,
  "models": [{
    "provider": "google",
    "model_id": "gemini-3-pro-image",
    "display_name": "Nano Banana Pro",
    "enabled": true,
    "credential_ready": true,
    "tasks": ["text-to-image", "image-to-image"],
    "aspect_ratios": ["1:1", "16:9", "9:16"],
    "image_sizes": ["1K", "2K", "4K"],
    "output_formats": ["png"],
    "max_reference_images": 14,
    "max_reference_bytes": 20971520
  }]
}
```

예시의 한도는 서버 설정 예시이며 모든 모델의 공통 한도가 아니다. 실제 참조 합산 예산은 해당 모델의 capability 값이 우선이다. 서버는 공급자 한도와 별도로 실제 요청 예산을 검증한다. 키가 없으면 `credential_ready=false`이고 생성 요청을 접수하지 않는다. `max_request_bytes`가 없는 이전 capability는 기존 64 MiB 클라이언트 상한을 유지하며, 필드가 있으면 `min(서버 상한, 64 MiB)`로 UTF-8 JSON 전체를 검사한다. 참조 합산 원본 바이트와 Base64를 포함한 요청 바이트를 함께 검사한다.

기존 `schema`, `version=1`, 기본 모델 필드, Task/결과 스키마는 유지한다. 확장 서버는 각 모델에 선택적으로 다음 `defaults`와 `option_schema`를 추가한다.

```json
{
  "defaults": {
    "task": "text-to-image",
    "ratio": "16:9",
    "image_size": "1K",
    "output_format": "png"
  },
  "option_schema": {
    "schema": "hmb-image-model-options-v1",
    "revision": "google-image-options-v1",
    "properties": {
      "temperature": {
        "type": "number", "label": "Temperature", "default": 1.0,
        "minimum": 0, "maximum": 2, "step": 0.1
      },
      "top_p": {
        "type": "number", "label": "Top P", "default": 0.95,
        "minimum": 0, "maximum": 1, "step": 0.05
      },
      "use_google_search": {
        "type": "boolean", "label": "Google Search", "default": false
      }
    }
  }
}
```

`defaults`는 기존 기본 옵션 목록에 실제 포함된 문자열만 허용한다. 옵션 스키마는 아래 제한된 타입을 사용하며 기본값을 필수로 제공한다.

| 선언 | 검증 및 클라이언트 처리 |
|---|---|
| `boolean` | JSON `true`/`false`만 허용. 숫자 0/1이나 문자열을 변환하지 않음 |
| `integer` | JSON 정수만 허용. `minimum`, `maximum`, 양수 `step`을 선택적으로 지정 |
| `number` | 유한한 정수·실수만 허용. `NaN`, 무한대, 불리언 거절. 범위와 양수 `step` 검증 |
| `string` | 문자열만 허용. `enum` 또는 `max_length`로 제한; 길이 기본 1024자, 선언 상한 4096자 |
| `enum` | 위 타입과 맞는 값 1~64개. 중복과 목록 밖 기본값 거절 |

모델별 옵션은 최대 32개다. 이름은 영문 소문자로 시작하는 영문 소문자·숫자·밑줄 1~64자다. 값이 생략되면 해당 모델이 광고한 기본값을 사용하지만, 명시한 `0`, `false`, 빈 문자열을 기본값으로 바꾸지 않는다. 미등록 키, 다른 모델에서 남은 숨김 키, 지원하지 않는 타입·검증 규칙은 제출 전에 거절한다. 임의 공급자 JSON이나 미래 옵션을 그대로 통과시키지 않는다. 지원하지 않는 스키마는 클라이언트·서버의 대응이 필요하며 저장한 입력을 다른 값으로 몰래 바꾸지 않는다.

## 순정 Google 모델별 입력 안내

아래 프로필은 설치된 Standard Google 이미지 노드에서 확인한 입력 안내다. 프로필 자체는 `enabled=false`, `credential_ready=false`이며 서버 준비 상태를 대체하지 않는다. 실제 제출은 현재 Broker capability만 사용한다.

| 모델 | 출력 크기 | 비율 | 고급 옵션 |
|---|---|---|---|
| Nano Banana Pro | `1K`, `2K`, `4K` | `1:1`, `3:2`, `2:3`, `3:4`, `4:3`, `4:5`, `5:4`, `9:16`, `16:9`, `21:9` | Temperature, Top P, Google Search |
| Nano Banana 2 | `512`, `1K`, `2K`, `4K` | `1:1`, `1:4`, `1:8`, `2:3`, `3:2`, `3:4`, `4:1`, `4:3`, `4:5`, `5:4`, `8:1`, `9:16`, `16:9`, `21:9` | 공통 옵션과 Google Image Search |

기본 입력은 텍스트 생성, `16:9`, `1K`, PNG다. Temperature는 1.0(0~2, 간격 0.1), Top P는 0.95(0~1, 간격 0.05), 검색은 모두 OFF다. Nano Banana 2의 `use_google_image_search` 옵션은 해당 모델 스키마에만 선언한다. Pro로 전환했을 때 숨겨진 이미지 검색 값이 남아 있어도 Pro 요청으로 전달하지 않는다.

서버 Google 어댑터는 모델별로 `generationConfig.temperature`, `topP`, `imageConfig.aspectRatio`와 `imageSize`를 매핑한다. 검색도 광고한 모델에서만 사용한다. 웹 검색 단독은 `google_search: {}`; 이미지 검색은 `google_search.searchTypes.imageSearch: {}`를 사용하며 웹 검색도 켰으면 `webSearch: {}`를 함께 포함한다. UI 힌트 대신 실제 선택 모델의 capability와 revision을 검증한다.

## 생성 요청

`POST /api/v1/generate/image` (`Idempotency-Key` = `client_request_id`)

```json
{
  "provider": "google",
  "model": "gemini-3-pro-image",
  "task": "text-to-image",
  "prompt": "사용자가 입력한 원문",
  "persistence_scope": "personal_local",
  "publish_to_reviews": false,
  "ratio": "1:1",
  "image_size": "1K",
  "output_format": "png",
  "reference_images": [],
  "client_request_id": "img-<unique-id>"
}
```

최초에는 요청당 이미지 1개다. 편집 작업의 참조는 검증된 PNG/JPEG/WebP data URI 순서대로 전달한다. 모델용 키·프로젝트·샷·게시 제목은 전달하지 않는다. 서버는 개인 이미지에 공용 프로젝트 기본값을 넣지 않는다.

기존 모델이 `option_schema`를 광고하지 않으면 위 **11필드만** 보낸다. 빈 `model_options`나 스키마 필드도 붙이지 않는다. 해당 서버에 고급 옵션을 요구하면 미지원으로 거절한다.

모델이 `option_schema`를 광고한 경우에만 다음 **두 필드**를 추가한다. `model_options`는 검증한 기본값과 사용자 지정값을 합친 해당 모델의 유효 옵션이며, revision은 현재 서버가 광고한 값과 정확히 같아야 한다.

```json
{
  "model_options": {
    "temperature": 1.0,
    "top_p": 0.95,
    "use_google_search": false
  },
  "model_options_schema_revision": "google-image-options-v1"
}
```

`auto_image_resize`는 로컬 참조 준비 옵션이며 요청 본문에 넣지 않는다. 도우미의 기본값은 OFF로 이전 호출의 원본 바이트 전달을 유지한다. ON인 경우에도 실제 참조 합산 예산 또는 전체 요청 예산을 넘을 때만 복사본을 재인코딩·축소한다. 가로세로 비율을 유지하며 자르거나 늘리지 않고 원본 파일을 덮어쓰지 않는다. 예산 안에 있으면 원본 참조 바이트를 그대로 보낸다. 처리 범위는 각 원본 32 MiB / 64 MiPixels, 전체 자동 처리 입력 128 MiB 이내다. 최선의 축소로도 한도에 들어가지 않으면 제출 전에 명확히 실패한다. 참조 축소가 생성 출력의 `image_size` 설정을 바꾸지는 않는다.

접수 및 `POST /api/v1/jobs/{job_id}/refresh` 응답:

```json
{
  "schema": "hmb-image-generation-job-v1",
  "version": 1,
  "job_id": "job-<durable-id>",
  "status": "succeeded",
  "provider": "google",
  "model": "gemini-3-pro-image",
  "client_request_id": "img-<unique-id>",
  "persistence_scope": "personal_local",
  "publish_to_reviews": false,
  "result": {
    "url": "<동일 Broker base>/api/assets/<43-character-token>",
    "mime_type": "image/png",
    "sha256": "<64 hexadecimal characters>"
  }
}
```

상태는 `queued`, `running`, `succeeded`, `failed`, `cancelled`, `expired`다. 성공 시 단일 `result`가 필수다. `client_request_lookup=true`이면 같은 사용자·같은 키의 client ID를 refresh 별칭으로 해석한다. 존재하지 않는 client ID를 조회해도 새 생성 요청을 만들지 않는다. 응답 유실 후에도 동일 키/Task를 복구하며 새로운 키로 자동 제출하지 않는다. 조회 간격은 30초, HTTP 요청 1회당 최대 대기는 300초다. 노드의 전체 조회 대기 한도는 별도이며 현재 기본 3600초다.

`queued` 또는 `running` 응답에 `submission_outcome_unknown=true`가 있거나 `error.code="image_submission_unknown"`이 있으면 공급자 접수 결과가 미확정인 상태다. 클라이언트는 즉시 자동 조회를 멈추고 로컬 체크포인트·표시 상태를 `submission_unknown`으로 기록한다. 원래 Broker·Task ID·client request ID·모델·저장 목적지는 유지하고, 원시 공급자 오류 본문 대신 접수 불명과 자동 조회 중지를 안내한다. 해당 Task가 완료되었다거나 과금이 없었다고 단정하지 않는다.

사용자는 **Retrieve Existing Image**로 동일 Task를 명시적으로 재조회한다. 체크포인트가 미확정인 동안 Run도 같은 Task 복구를 사용하며 새 UUID나 생성 POST를 만들지 않는다. 조회 결과가 여전히 미확정이면 다시 자동 조회를 멈춘다. 서버가 검증 가능한 성공 결과를 반환하면 같은 Task의 이미지를 로컬에 저장하며, 기존 파일과 원래 요청을 보존한다. 이 체크포인트와 복구 동작은 워크플로 저장·재오픈 후에도 유지한다.

Run 시점에 모델·기본 설정·고급 옵션·참조 준비 결과를 불변 스냅샷으로 고정한다. 제출 직전 재검증에서도 같은 옵션과 revision을 사용하며, 카탈로그가 바뀌어 일치하지 않으면 POST 전에 중단한다. 기존 체크포인트의 Broker 주소·client request ID·Task ID·모델·원본 저장 경로를 유지한다. 진행 중 작업, 접수 불명, 서버 완료 후 로컬 저장 실패를 복구할 때는 현재 UI 모델·옵션·기본값을 재해석하지 않고 기존 ID를 조회한다.

다운로드는 인증된 동일 Broker `/api/assets/…` 경로만 허용한다. 리디렉션으로 토큰을 전달하지 않는다. 실제 이미지 디코드·MIME·크기·가능한 SHA-256 검증 후 원자적으로 로컬에 저장하며 기존 파일은 덮어쓰지 않는다. 저장 성공 후 반복 조회는 검증한 기존 파일을 재사용한다. 저장만 실패한 경우에도 다음 Run은 이미 완료된 동일 Task를 복구한다.

## 모델별 비용 집계와 서버 확장 조건

개인용 이미지 미게시와 비용 계량 원장은 별개다. 서버는 사용자 인증 계정, 공급자, 실제 모델 ID, Broker job ID, client request ID를 연결하고 다음을 기록한다.

| 항목 | 서버 처리 |
|---|---|
| 가격·집계 기준 | 모델 ID, 해상도·품질 등 과금 옵션, 가격표 버전, 통화, 공급자가 보고한 토큰/이미지 사용량 |
| 접수 | 동일 사용자·동일 idempotency key를 한 작업으로 예약하고, 다른 본문 재사용은 거절 |
| 확정 | 공급자 요청 ID/usage와 연결해 비용을 한 번만 확정; 실제 사용량과 추정치를 구분 |
| 실패·응답 유실 | 접수 불명 상태를 보존; 실패라는 이유만으로 비용 0 또는 무료 재생성으로 처리하지 않음 |
| 재조회·다운로드 | 새 모델 호출·중복 비용 항목을 만들지 않음 |
| 운영 통계 | 권한 있는 모델별·사용자별 비용 합계만 제공; 개인 이미지가 작업관리 영상 목록에 표시되지 않음 |

클라이언트가 API 키 또는 로컬 추정 금액을 서버의 과금 근거로 제출하지 않는다. 원본 이미지의 무기한 중앙 보관은 요구하지 않는다. 개인 이미지 작업과 임시 결과 보관은 기존 영상·리뷰에서 분리하며 보관 기간은 서버 정책을 따른다.

추가 모델·고급 옵션을 활성화하려면 서버에서 다음을 함께 구현해야 한다.

1. 모델 registry를 capability·요청 검증·공급자 매핑·실제 응답 모델 확인·가격 집계에서 공통으로 사용한다. Pro 상수를 목록에만 추가하는 방식으로 확장하지 않는다.
2. `option_schema`를 광고한 모델에만 두 확장 필드를 허용하고, 해당 revision/타입/범위/미등록 키를 다시 검증한다. 기존 11필드 요청의 호환을 유지한다.
3. 유효 고급 옵션과 revision을 새 작업의 fingerprint·예약된 요청·가격 스냅샷에 포함한다. 동일 사용자·키로 다른 옵션을 재접수하면 409이며 공급자를 다시 호출하지 않는다.
4. 이전 11필드 작업의 fingerprint와 Task 조회를 유지한다. 기존 client ID의 재접수는 당시 예약한 스냅샷과 비교하며 새 서버 기본값으로 바꾸지 않는다. 미확정 요청을 무료 재시도로 취급하지 않는다.
5. 각 모델의 순정 옵션·출력 크기·참조 한도와 실제 요청 직렬화, 사용량 집계를 무과금 fixture로 검증한 뒤 별도 승인된 키 등록·실제 생성 확인을 진행한다.

## 서버 구현과 회귀 검사 경계

별도 이미지 adapter·내구성 작업·소유자 다운로드·usage 원장이 같은 요청 신원을 유지해야 한다. 아래 경계는 패키지 검사뿐 아니라 서버 회귀 검사에서도 확인하며 운영 활성화나 실제 모델 응답 검증을 대신하지 않는다.

1. 영상 전용 공급자 마이그레이션과 fingerprint를 이미지 모델 registry·요청 신원에서 분리한다.
2. `generate/image`와 이미지 capability를 영상 생성 경로와 분리하고 동일 사용자·키의 중복 생성을 막는다.
3. 동기 이미지 결과에 공급자 job ID가 없어도 `Broker job_id + output_id`로 소유 결과를 정확히 연결한다.
4. 웹 목록뿐 아니라 상세·통계·직접 접근 API에서도 `personal_local` 이미지를 리뷰 작업에서 제외한다. casecard를 생략하는 것만으로는 부족하다.
5. 생성 접수·usage 원장·소유자 결과 다운로드에 대해 키 미등록/중복 클릭/전송 시간 초과/재시작/조회/로컬 저장 실패를 무과금 fixture로 검증한다. 접수 불명 응답 후 자동 조회 중지·동일 Task 회수·저장본 재오픈·새 생성 없음도 확인한 뒤 실제 생성 검증을 별도로 진행한다.

공식 모델 자료: [Google 이미지 생성](https://ai.google.dev/gemini-api/docs/image-generation), [Nano Banana Pro 모델](https://ai.google.dev/gemini-api/docs/models/gemini-3-pro-image). 공급자 키는 서버에만 설치한다.
