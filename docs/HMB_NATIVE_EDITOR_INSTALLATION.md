# HMB Override 네이티브 UI 적용

HMB 업데이트는 Griptape의 Git Update/Override로 라이브러리와 네이티브 UI를 함께 적용한다. 별도 ZIP 다운로드나 PowerShell 설치는 일반 업데이트 과정에 필요하지 않다. 이 규칙은 앞으로 추가되는 HMB 도구에도 적용한다.

## 업데이트 순서

1. Griptape에서 기존 HMB Git 라이브러리의 Update/Override를 실행한다.
2. 새 라이브러리 등록 시 네이티브 UI 동기화가 자동 실행된다. Git으로 받은 patcher·JavaScript helper·descriptor를 검증하고 지원되는 편집기 파일을 백업한 뒤 원자 교체한다.
3. 현재 작업을 저장하고 Griptape를 완전히 종료한 뒤 다시 실행한다. 실행 중인 Python 모듈과 편집기 JavaScript는 재시작 전까지 메모리에 남을 수 있다.
4. 기존 워크플로에서 통합 헤더·포트·접기 복원과 연결된 노드의 삭제 보호를 확인한다. 화면의 native v2 표시와 Engine 보호 준비 상태가 확인되기 전에는 완전 적용으로 판정하지 않는다.

자동 동기화는 앱을 강제로 종료하거나 워크플로를 비우지 않는다. `ReloadAllLibrariesRequest`는 내부적으로 객체를 비우므로 업데이트 완료를 위한 자동 호출에 사용하지 않는다. 실행 중인 화면에 React 소유의 포트나 삭제 콜백을 임의 주입하지 않는다.

Git 라이브러리의 **Update Override**와 라이브러리 **Download의 덮어쓰기**는 다르다. Download 덮어쓰기는 SDK가 기존 폴더를 먼저 삭제할 수 있으므로, 기존 사용자 파일을 보존하는 Update Override를 사용한다. 자동 UI 동기화가 다운로드 이전의 삭제를 소급 보호하지는 않는다.

## 지원 확인과 복구

- 지원 편집기는 `0.128.1`의 `index-DEZU41rc.js`다. 정확한 원본·현재 패치·검토된 이전 패치 3개의 SHA256을 허용 목록으로 검사한다. Griptape 원본 번들은 배포하지 않는다.
- SDK는 `griptape-nodes 0.101.3` 이상이어야 한다. SDK를 실행하거나 import하지 않고 metadata와 AST에서 `current_engine`, `EventManager.add_pre_dispatch_hook`, `EventManager.remove_pre_dispatch_hook`, `EventManager.register_request_handlers`를 확인한다.
- Git 등록 경로의 지원 파일과 고정된 앱 편집기 위치만 사용한다. 캐시된 Python helper를 다시 import하는 대신 별도 격리 프로세스에서 현재 Git 파일을 읽는다.
- 복구 원본·후보·영수증은 Git 체크아웃 밖 `%LOCALAPPDATA%\HMB_GP_Production\native-editor-installs`에 보관한다. Git reset으로 복구 자료가 지워지지 않는다.
- 공유 잠금을 사용하고 교체 직전에 SDK·소스·편집기 해시를 다시 확인한다. 같은 패치면 다시 쓰지 않는다. 실패하면 이 작업이 쓴 후보에 대해서만 원본을 복구한다.
- 파일이 잠겼으면 원본을 유지하고 `pending` 상태를 반환한다. 지원하지 않는 편집기·알 수 없는 해시·손상된 지원 파일은 `unsupported` 또는 `error`로 표시하며 성공으로 간주하지 않는다.
- 디스크 적용(`disk_ready`)과 실행 중 화면 적용을 구분한다. 자동 적용 결과의 `renderer_verified`는 항상 false이며 정상 재시작 뒤 별도로 확인한다.
- 기존 워크플로·샷·Task ID·미디어·설정·권한을 변경하지 않는다. 생성 작업이나 Broker 서버 업데이트를 실행하지 않는다.

기존 Runtime ZIP 설치기는 별도의 수동 복구 수단으로 남긴다. 이 경로는 계속 앱 완전 종료를 요구하며, Override 전용 디스크 동기화가 기존 설치기의 종료 검사나 복구 규칙을 완화하지 않는다.

## 이미지 프로젝트 위치

이미지 라이브러리는 `P:\projects\<프로젝트>\Ai_Ct_image`를 프로젝트의 이미지 경계로 사용한다. 현재 위치는 `P:\projects\superwings12\Ai_Ct_image`와 `P:\projects\Katuri8\Ai_Ct_image`다. 같은 공유 위치의 UNC 표기는 `\\192.168.200.19\v\projects\<프로젝트>\Ai_Ct_image`다.

이전 저장본의 알려진 주소 문자열은 새 위치로 한 번 변환한다. 이전 폴더를 조회하거나 카탈로그·JSON 복구 위치로 사용하지 않는다. 기존 샷·묶음 연결·ID·결과를 유지하며 공유 파일을 자동 이동하거나 다시 등록하지 않는다.

## 검증 증빙

공개 `.github/hmb-release-parity.json`은 검증한 로컬 짝수 버전 후보와 다음 팀원 홀수 버전의 정규화된 배포 파일 지문을 고정한다. ZIP은 재현 가능한 무결성·동등성 증빙에도 사용하며, 사용자의 정상 업데이트에 별도 ZIP 설치를 요구하지 않는다.

Git 체크아웃 갱신, 자동 디스크 적용, SDK 보호 등록, 재시작 후 실제 화면을 각각 구분해 기록한다. 소스·패키지 검사나 `disk_ready`만으로 실제 화면 검사를 통과했다고 보고하지 않는다.
