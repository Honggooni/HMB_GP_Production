# Griptape Desktop 업데이트 검증

팀 작업 PC에서는 현재 승인된 Desktop 버전을 유지한다. HMB 라이브러리는 기존 Git Update/Override 경로로 업데이트한다.

1. 작업을 저장하고 Desktop을 종료한다. 관리자는 팀 Windows PC에 `tools/Set-GriptapeUpdateHold.ps1`을 배포한다. 이 스크립트는 기존 정책 항목을 보존하면서 `%ProgramData%\GriptapeNodes\policy.json`의 `disableUpdates`를 설정한다. 관리자 정책이 적용되기 전 한 계정에서 사용하려면 `-CurrentUser`로 실행한다. 새 Windows 세션 또는 업데이트 잠금 환경 변수를 상속한 프로세스에서 Desktop을 시작한다. [Griptape 공식 정책](https://docs.griptapenodes.com/en/stable/enterprise/disabling_app_updates/)
2. 별도 검증 PC에서 새 Desktop을 설치하고, 그 Desktop에 포함된 Python으로 `tools/check_griptape_upgrade.py --report-dir <검사 폴더>`를 실행한다. 실제 SDK의 노드 생성·연결·삭제 보호와 저장·재열기를 검사하고, 네이티브 편집기 파일이 검토된 파일인지 기록한다.
3. 검증 PC에서 샷 관리 화면, 저장·재열기, 연결된 노드의 삭제 거부를 실제로 확인한다. 업그레이드 도구의 성공은 SDK와 디스크 파일 검사 결과다. 실제 화면 결과를 함께 기록한 뒤 관리자 설치본을 팀에 배포한다.
4. 적용 전 Desktop 설치본과 HMB Git 태그를 함께 보관한다. 새 버전에 문제가 있으면 공식 설치본으로 복구하고 작업 파일은 기존 위치에서 연다.

Team v0.8.59는 SDK 0.104의 연결과 저장 경로를 복구한다. Editor 0.130 전용 헤더 연동과 실제 화면 검증은 별도로 남아 있다.

## Team v0.8.59 compatibility check

The Team runtime stays on v0.8.59. On SDK 0.104.0, the installed-SDK checks passed for connected-node deletion protection and Prompt workflow save/reopen. The Editor 0.130.0 stock deletion regression also passed. Native Editor integration and interactive Team Desktop use are outside this evidence, so the upgrade preflight still rejects promotion of this editor profile. The Local Rodong Mart overlay is outside the Team runtime.
