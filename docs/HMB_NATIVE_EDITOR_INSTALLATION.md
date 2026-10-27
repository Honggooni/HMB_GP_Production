# HMB 네이티브 UI 설치 범위

팀원 v0.8.33은 검증된 로컬 v0.8.32 수정본과 기능이 같은 배포본이다. 로컬 v0.8.34는 팀원 v0.8.33의 기능을 유지하고 버전 표기만 변경한다. 패키지 검증, 실제 설치, 실행 중인 앱 확인은 각각 별도 증빙으로 기록한다.

## 설치 경로

완전한 네이티브 UI를 적용하려면 Runtime ZIP을 풀고 Griptape를 완전히 종료한 상태에서 포함된 `Install_HMB_GP_Production.ps1`을 실행한다. 일반 Git Update/Override는 라이브러리 코드를 갱신하며 네이티브 편집기 패치는 설치하지 않는다.

**Git Update의 성공 메시지와 최신 라이브러리 버전만으로 전체 설치 완료를 판단하면 안 된다.** Git Update는 Python 라이브러리를 다시 등록하지만 앱 편집기 번들과 실행 중인 코드까지 교체하지 않는다. `업데이트 설치 마무리 필요` 안내가 나타나거나 기존 보라색 제목 막대·사각 크기 조절 표시가 남으면 아래 공식 ZIP 설치를 완료한다. 단순 재시작만으로 누락된 편집기 패치가 설치되지는 않는다. 실행 중 자동 파일 교체·자동 종료·백그라운드 설치는 하지 않는다.

ZIP에는 라이브러리 런타임 60개와 설치 지원 파일 7개, manifest 및 SHA256 목록이 포함되어 총 69개 항목이 들어간다. 네이티브 UI용 지원 파일은 patcher, JavaScript helper, 지원 버전·해시 descriptor 3개다. Griptape 원본 편집기 번들 자체를 배포하지 않는다.

1. GitHub Release의 해당 홀수 버전 Runtime ZIP과 `.sha256`을 내려받아 파일 해시를 확인한다.
2. 현재 워크플로를 저장하고 Griptape를 완전히 종료한다.
3. ZIP을 새 폴더에 풀고 `HMB_GP_Production` 폴더에서 PowerShell을 연다.
4. `powershell -NoProfile -ExecutionPolicy Bypass -File .\Install_HMB_GP_Production.ps1`을 실행한다.
5. 설치가 성공한 뒤 Griptape를 다시 열어 라이브러리 버전과 기존 워크플로를 확인한다.

기본 라이브러리 위치는 Windows 문서 폴더의 `GriptapeNodes\libraries\HMB_GP_Production`이다. 문서 폴더를 다른 드라이브로 옮긴 PC에서도 Windows가 반환한 실제 문서 위치를 사용한다. 설치기의 `-TargetRoot`도 이 위치만 허용하며, 다른 임의 폴더나 현재 라이브러리 내부에서 설치기를 실행하면 중단한다. Git 체크아웃 폴더에서 설치기를 바로 실행하지 말고, 검증된 ZIP을 라이브러리 바깥의 새 폴더에 풀어 실행한다.

## 지원 확인과 복구

- 현재 지원 대상은 Griptape editor `0.128.1`의 `index-DEZU41rc.js`다. 버전과 정확한 원본 SHA256을 함께 검사한다.
- SDK는 `griptape-nodes 0.101.3` 이상이어야 한다. 설치기는 SDK를 실행하거나 import하지 않고 설치된 패키지 metadata와 Python AST를 읽어 `current_engine`, `EventManager.add_pre_dispatch_hook`, `EventManager.remove_pre_dispatch_hook`, `EventManager.register_request_handlers`가 실제로 있는지 검사한다. `griptape-nodes-engine`의 별도 버전 숫자로 이 검사를 대신하지 않는다.
- 필수 API가 없거나 SDK 파일을 읽을 수 없으면 첫 라이브러리 이동 전에 중단한다. 준비 이후 SDK가 바뀌어도 적용을 중단하며, 기존 라이브러리와 편집기 복구는 허용한다. SDK를 임의로 pip 교체하지 말고 지원되는 Griptape 앱 업데이트 후 공식 설치기를 다시 실행한다.
- 이미 검증된 동일 패치가 설치되어 있으면 편집기 파일을 다시 쓰지 않는다.
- 허용 목록의 이전 패치 2개는 각각 전체 번들과 해당 helper의 SHA256을 확인한 뒤 helper만 교체한다. 완성된 번들의 SHA256도 새 후보와 같아야 하며, 실패하면 직전에 사용하던 패치 원문을 복구한다.
- 다른 버전·알 수 없는 패치·손상된 지원 파일·실행 중인 Griptape를 발견하면 라이브러리 교체 전에 중단한다.
- 적용 전에 복구 데이터를 `%LOCALAPPDATA%\HMB_GP_Production\native-editor-installs\<설치 ID>`에 보관한다.
- 편집기 적용 또는 설치 영수증 작성이 실패하면 라이브러리와 편집기를 함께 복구한다. 준비 이후 제삼자가 편집기 파일을 변경했다면 그 파일을 덮어쓰지 않고 복구 오류와 경로를 명시한다.
- 기존 워크플로·사용자 설정·출력 결과는 유지한다. 설치는 생성 작업을 실행하거나 Broker 설정을 변경하지 않는다.

설치 영수증의 `native_editor_patch.sdk_preflight`는 파일 기준 호환성 증빙이다. 실행 중 보호가 등록됐다는 증빙과는 구분한다. 재시작 후에는 기존 워크플로에서 통합 헤더·포트·접기 복원을 확인하고, 연결된 HMB 노드의 삭제가 거부되며 연결 해제한 노드는 삭제되는지도 진단 복사본에서 확인한다. 실제 사용자 샷을 지워서 검사하지 않는다.

## 이미지 프로젝트 위치

이미지 라이브러리는 `P:\projects\<프로젝트>\Ai_Ct_image`만 프로젝트의 이미지 경계로 사용한다. 현재 위치는 `P:\projects\superwings12\Ai_Ct_image`와 `P:\projects\Katuri8\Ai_Ct_image`다. 매핑 드라이브를 사용할 수 없는 PC에서는 같은 공유 위치인 `\\192.168.200.19\v\projects\<프로젝트>\Ai_Ct_image`를 사용한다.

이전 저장본의 알려진 경로 문자열은 새 위치로 한 번 변환한다. 이전 폴더를 조회하거나 카탈로그·JSON 복구 위치로 사용하지 않는다. 기존 샷·묶음 연결·ID·결과는 유지하며, 공유 파일을 자동으로 이동하거나 다시 등록하지 않는다.

## 검증 증빙

공개 `.github/hmb-release-parity.json`은 검증된 로컬 v0.8.32 수정본 → 팀원 v0.8.33의 정규화된 배포 파일 지문과 기준 ZIP SHA256을 고정한다. 팀원 릴리스는 `--check-parity-proof`를 통과해야 한다. 로컬 v0.8.34는 별도로 팀원 v0.8.33 ZIP과 동등성을 검사하며 공개 32→33 증빙을 유지한다.

`package_runtime_release.py --check-local-parity-proof ... --output <ZIP>`는 짝수 로컬 후보의 실제 ZIP·현재 소스·증빙 SHA256을 비교하며 `team_release_authorized=false`를 반환한다. 이 결과 자체는 팀원 릴리스 승인이나 실제 앱 검사 결과가 아니다. 검사 보고서는 자동 회귀, 설치 파일 해시, 실제 SDK·앱·DCC 관찰과 미실행 항목을 구분한다.
