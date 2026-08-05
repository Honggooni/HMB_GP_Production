# Security

보안 취약점이나 운영 경로를 공개 이슈에 게시하지 마십시오. 프로젝트
관리자에게 비공개 채널로 영향받는 버전, 재현 조건, 예상 영향과 최소
재현 자료를 전달하십시오. API 키, 정책 본문, 서명 키, 내부 미디어는
보고서에도 포함하지 않습니다.

## Repository visibility

이 저장소와 릴리스에는 승인된 HMB 운영자가 사용하는 내부 호스트 및
공유폴더 기본값이 포함됩니다. 저장소와 GitHub Release는 반드시
**Private**으로 유지하십시오. 공개 전환이 필요하면 내부 기본값을 모두
환경변수나 관리자 설정으로 치환하고 전체 릴리스 보안 검사를 다시
통과해야 합니다.

## Trust boundaries

- HMB 정책이 적용되는 유일한 경로는 등록된 정확한
  `HMBPromptLibrary.PROMPT_OUT -> HMBAgentLibrary.prompt` 직접 연결입니다.
  복사된 클래스, 같은 이름의 다른 라이브러리, 메타데이터 릴레이 또는
  Asset/Picker 직접 연결은 이 경계로 인정하지 않습니다.
- 정책은 배포물 밖의 관리자 지정 경로에서 읽는 서명된 실행 데이터이며,
  고정 schema/version/contract digest와 서명이 모두 일치할 때만 사용됩니다.
- 정책 payload, private signing key, 복호화 키 및 API 키는 소스, ZIP,
  워크플로, 로그 또는 노드 출력에 포함하지 않습니다. 클라이언트에는
  서명 검증용 RSA 공개키만 둡니다.
- HMB Prompt 직접 연결에서 정책이 없거나 읽을 수 없거나 검증되지 않으면
  출력을 비우고 실행을 중단합니다. 순정 Agent, 도구 또는 모델 호출로
  대체하지 않습니다. 연결 상태를 안전하게 확인할 수 없는 경우도
  fail-closed 처리합니다.
- 비 HMB 요청만 정책을 읽지 않고 표준 실행 경로를 사용할 수 있습니다.
  Standard Agent는 등록된 canonical host package 또는 사용자가 명시한
  정확한 package root에서만 로드합니다.
- 정책 공유폴더 권한은 SMB share와 NTFS ACL을 함께 적용합니다. 일반
  사용자는 읽기만, 정책 관리자는 생성·쓰기·이름 변경·삭제 권한을 갖도록
  분리합니다.
- 로컬 관리자 권한을 가진 사용자가 실행 중 메모리나 클라이언트 코드를
  검사하는 것까지 클라이언트 암호화로 막을 수는 없습니다. 그 수준의
  통제가 필요하면 정책 적용과 모델 실행을 서버 서비스로 이동해야 합니다.
- Maya runner의 읽기·쓰기·삭제 대상은 검증된 작업 root 아래로 제한하고
  symlink, junction 및 reparse point를 거부합니다.
- Image Asset 등록은 project-root containment와 실제 이미지 decode/header
  검증을 통과해야 합니다. 선택 미디어가 없거나 읽을 수 없으면 생성
  입력을 부분적으로 전달하지 않고 명시적으로 차단합니다.

## Volcengine credential boundary

- 사용자 소유 Ark 키는 Griptape `Settings > Secrets > ARK_API_KEY`에만
  저장합니다. 노드 속성, 워크플로 JSON, 소스, 명령행, 스크린샷, 로그,
  진단 payload 또는 릴리스에 넣지 않습니다.
- `HMBSeedance20VideoGeneration`은 실행 시점에만 키를 읽고 고정된 공식
  Ark API origin으로만 전송합니다. 서명된 결과 URL이나 참조 영상
  업로드 서비스에는 Ark 키를 전달하지 않습니다.
- Griptape Cloud 임시 업로드에는 별도의 `GT_CLOUD_API_KEY`를 사용하며
  `GT_CLOUD_BUCKET_ID`는 선택 사항입니다.
- Volcengine TOS를 선택하면 별도 최소 권한 IAM 자격 증명
  `TOS_ACCESS_KEY_ID`, `TOS_SECRET_ACCESS_KEY`, `TOS_BUCKET_NAME`을
  사용합니다. Ark 키와 TOS 키는 서로의 요청에 사용하지 않습니다.
- TOS endpoint는 공식 `tos-*.volces.com` HTTPS host로 제한합니다. 임시
  object 이름은 무작위로 만들고 실행 종료 후 삭제하며, 비정상 종료에
  대비한 짧은 bucket lifecycle을 별도로 설정합니다.
- 과금 가능한 create POST는 한 번만 시도하며 자동 재시도하지 않습니다.
  모호한 제출 진단에는 prompt, header, payload, 서명 URL, 원본 예외 또는
  미디어를 저장하지 않습니다.

## Seedance usage-ledger boundary

- 사용량 기록은 `HMBSeedance20VideoGeneration`만 작성합니다. 로그인한
  Griptape `user_id`와 task ID를 검증하고 중복 기록을 방지합니다.
- 기록 allowlist에는 task identity, status, model/options, token count,
  가격 snapshot과 timestamp만 포함합니다. prompt, API 키, authorization,
  reference/result URL, 미디어 payload 및 전체 provider response는
  포함하지 않습니다.
- 이벤트는 로컬 atomic queue에 먼저 기록한 뒤 백그라운드에서 사용자별
  네트워크 JSON으로 동기화합니다. 네트워크 실패가 새 생성 POST를
  만들거나 결과를 변경해서는 안 됩니다.
- 손상된 기존 ledger는 덮어쓰지 않으며, 동기화하지 못한 로컬 이벤트는
  다음 실행에서 다시 처리합니다.

## Release verification

- 배포물은 `resources/build_release.py`로 생성한
  `HMB_GP_Production.zip`, `release-manifest.json`, `SHA256SUMS` 세 파일을
  함께 관리합니다.
- 같은 소스의 연속 빌드는 동일한 ZIP SHA-256을 생성해야 합니다.
- `resources/tests/HMB_Public_Release_Security_Regression.py`로 API 키,
  자격 증명 파일, 정책 payload, private key, 로컬 생성물 및 금지 경로가
  ZIP에 없는지 확인합니다.
- 정책을 변경할 때는 offline signing-key 보관소에서 서명하거나 명시적인
  public-key rotation 절차를 사용합니다. RSA 공개키는 암호화 또는
  복호화 키가 아니라 무결성 검증용입니다.
