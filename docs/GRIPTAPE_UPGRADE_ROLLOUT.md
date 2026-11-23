# Griptape Desktop 업데이트 검증

팀원 PC와 로컬 PC는 Griptape Desktop의 기본 업데이트 기능을 사용한다. HMB 라이브러리는 기존 Git Update/Override 경로로 업데이트한다.

1. 작업을 저장하고 Desktop의 기본 업데이트 절차를 따른다. 새 SDK·Editor 조합에서는 아래 검사를 거쳐 HMB 화면 연동의 적용 여부를 결정한다.
2. 별도 검증 PC에서 새 Desktop을 설치하고, 그 Desktop에 포함된 Python으로 `tools/check_griptape_upgrade.py --report-dir <검사 폴더>`를 실행한다. 실제 SDK의 노드 생성·연결·삭제 보호와 저장·재열기를 검사하고, 네이티브 편집기 파일이 검토된 파일인지 기록한다.
3. 검증 PC에서 샷 관리 화면, 저장·재열기, 연결된 노드의 삭제 거부를 실제로 확인한다. 업그레이드 도구의 성공은 SDK와 디스크 파일 검사 결과다. 실제 화면 결과를 함께 기록한 뒤 관리자 설치본을 팀에 배포한다.
4. 적용 전 Desktop 설치본과 HMB Git 태그를 함께 보관한다. 새 버전에 문제가 있으면 공식 설치본으로 복구하고 작업 파일은 기존 위치에서 연다.

릴리스 보고서에는 등록된 HMB 노드 수와 실제로 실행한 연결 경로를 각각 기록한다. 연결 오류를 수정하면 재현한 입력, 기존 샷 선택, 반복 실행, 다음 노드가 받은 결과를 해당 경로의 필수 회귀 검사에 포함한다. 예를 들어 ImageAsset 검사는 합성 JPEG를 Standard LoadImage로 열고 기존 프로젝트 이미지와 함께 HMBPrompt에 전달된 순서를 확인한다. 사용한 SDK와 Standard 버전, 실제 Desktop 화면에서 확인한 범위, 미실행 항목을 함께 남긴다.

별도 워크트리에서 배포할 때는 Team 게시물과 Local 설치 검증이 끝난 뒤 개발 PC의 배포 완료 절차에서 다음 명령을 실행한다. 팀원 PC의 일반 설치 절차는 이 명령을 사용하지 않는다.

```powershell
python tools/sync_published_workspace.py --workspace C:\HMB_GP_Production --tag <Team태그> --verified-stage <검증폴더>
```

검증 폴더의 `publication/verified.json`, `local-verified.json`과 실제 설치 영수증이 같은 배포를 가리켜야 한다. 채팅 작업 폴더의 `main`이 깨끗하고 원격 `main`과 Team 태그가 검증 커밋을 가리키면 fast-forward한다. 작업 중인 변경이나 분기된 커밋이 있으면 보존하고 중단한다. 출력의 `fast_forwarded` 또는 `already_current`와 함께 완료를 기록한다.
동기화할 때 실제 설치된 Local 버전이 게시된 Team 버전보다 높은지도 확인한다.

Team v0.8.59는 SDK 0.104의 연결과 저장 경로를 복구한다. Editor 0.130 전용 헤더 연동과 실제 화면 검증은 별도로 남아 있다.

## Team v0.8.59 compatibility check

The Team runtime stays on v0.8.59. On SDK 0.104.0, the installed-SDK checks passed for connected-node deletion protection and Prompt workflow save/reopen. The Editor 0.130.0 stock deletion regression also passed. Native Editor integration and interactive Team Desktop use are outside this evidence, so the upgrade preflight still rejects promotion of this editor profile. The Local Rodong Mart overlay is outside the Team runtime.
