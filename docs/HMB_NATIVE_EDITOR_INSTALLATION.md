# HMB 네이티브 UI 설치 범위

팀원 v0.8.31은 검증된 로컬 v0.8.30과 기능이 같은 배포본이다. 로컬 v0.8.32는 팀원 v0.8.31의 기능을 유지하고 버전 표기만 변경한다. 패키지 검증, 실제 설치, 실행 중인 앱 확인은 각각 별도 증빙으로 기록한다.

## 설치 경로

완전한 네이티브 UI를 적용하려면 Runtime ZIP을 풀고 Griptape를 완전히 종료한 상태에서 포함된 `Install_HMB_GP_Production.ps1`을 실행한다. 일반 Git Update/Override는 라이브러리 코드를 갱신하며 네이티브 편집기 패치는 설치하지 않는다.

ZIP에는 라이브러리 런타임 60개와 설치 지원 파일 7개, manifest 및 SHA256 목록이 포함되어 총 69개 항목이 들어간다. 네이티브 UI용 지원 파일은 patcher, JavaScript helper, 지원 버전·해시 descriptor 3개다. Griptape 원본 편집기 번들 자체를 배포하지 않는다.

1. GitHub Release의 해당 홀수 버전 Runtime ZIP과 `.sha256`을 내려받아 파일 해시를 확인한다.
2. 현재 워크플로를 저장하고 Griptape를 완전히 종료한다.
3. ZIP을 새 폴더에 풀고 `HMB_GP_Production` 폴더에서 PowerShell을 연다.
4. `powershell -NoProfile -ExecutionPolicy Bypass -File .\Install_HMB_GP_Production.ps1`을 실행한다.
5. 설치가 성공한 뒤 Griptape를 다시 열어 라이브러리 버전과 기존 워크플로를 확인한다.

기본 라이브러리 위치는 Windows 문서 폴더의 `GriptapeNodes\libraries\HMB_GP_Production`이다. 사용자 지정 위치는 설치기의 `-TargetRoot`로 지정한다. 문서 폴더를 다른 드라이브로 옮긴 PC에서도 Windows가 반환한 실제 문서 위치를 사용한다.

## 지원 확인과 복구

- 현재 지원 대상은 Griptape editor `0.128.1`의 `index-DEZU41rc.js`다. 버전과 정확한 원본 SHA256을 함께 검사한다.
- 이미 검증된 동일 패치가 설치되어 있으면 편집기 파일을 다시 쓰지 않는다.
- 허용 목록의 이전 패치 1개는 전체 번들과 기존 helper의 SHA256을 확인한 뒤 helper만 교체한다. 완성된 번들의 SHA256도 새 후보와 같아야 하며, 실패하면 직전에 사용하던 패치 원문을 복구한다.
- 다른 버전·알 수 없는 패치·손상된 지원 파일·실행 중인 Griptape를 발견하면 라이브러리 교체 전에 중단한다.
- 적용 전에 복구 데이터를 `%LOCALAPPDATA%\HMB_GP_Production\native-editor-installs\<설치 ID>`에 보관한다.
- 편집기 적용 또는 설치 영수증 작성이 실패하면 라이브러리와 편집기를 함께 복구한다. 준비 이후 제삼자가 편집기 파일을 변경했다면 그 파일을 덮어쓰지 않고 복구 오류와 경로를 명시한다.
- 기존 워크플로·사용자 설정·출력 결과는 유지한다. 설치는 생성 작업을 실행하거나 Broker 설정을 변경하지 않는다.

## 검증 증빙

공개 `.github/hmb-release-parity.json`은 검증된 로컬 v0.8.30 → 팀원 v0.8.31의 정규화된 배포 파일 지문과 기준 ZIP SHA256을 고정한다. 팀원 릴리스는 `--check-parity-proof`를 통과해야 한다. 로컬 v0.8.32는 별도로 팀원 v0.8.31 ZIP과 동등성을 검사하며 공개 30→31 증빙을 덮어쓰지 않는다.

`package_runtime_release.py --check-local-parity-proof ... --output <ZIP>`는 짝수 로컬 후보의 실제 ZIP·현재 소스·증빙 SHA256을 비교하며 `team_release_authorized=false`를 반환한다. 이 결과 자체는 팀원 릴리스 승인이나 실제 앱 검사 결과가 아니다. 검사 보고서는 자동 회귀, 설치 파일 해시, 실제 SDK·앱·DCC 관찰과 미실행 항목을 구분한다.
