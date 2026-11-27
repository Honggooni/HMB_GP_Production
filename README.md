# HMB GP Production

Team **v0.9.77**는 Griptape Desktop **0.31.0**용 HMB 노드 라이브러리입니다.

## 샷 실행과 재시도

- 사운드·이미지·비디오 피커가 현재 샷의 선택을 Prompt에 제공합니다. Prompt 앞에 있는 분석기는 Prompt로, 뒤에 있는 분석기는 `To Agent`로 결과를 전달합니다. 사용 중인 분석 원본을 바꾸면 해당 분석을 마친 뒤 다음 단계로 넘어갑니다.
- 이미지 선택이나 순서를 바꾸면 해당 샷의 Prompt, Agent, Generator가 다시 확인 대상이 됩니다. VideoPicker와 Sound의 완료 상태는 유지됩니다. 영상을 바꾸거나 재분석하면 그 분석 결과를 사용하는 단계가 다시 확인 대상이 됩니다.
- Agent에서 샷을 실행하면 현재 Prompt와 뒤쪽 분석기의 결과를 읽습니다. Generator에서 실행하면 앞단의 변경을 확인하고, 입력이 달라졌을 때 Agent가 다시 분석합니다.
- 480p Draft가 완료되면 전용 Final 버튼으로 최종본을 만듭니다. 설정이나 해상도를 바꾸면 일반 실행이 열리고, 원래 샷 입력과 Draft 설정으로 돌아오면 사용 가능한 기존 Draft의 Final 버튼이 다시 표시됩니다. Only 모드에서 탐색기로 원본을 덮어썼다면 해당 파일을 다시 선택하세요.
- 브로커 연결이 끊기면 같은 작업 ID를 먼저 조회합니다. 최종 실패가 확인되면 사유를 표시하고 종료합니다.
- 새 브로커에서는 480p Draft 생성 후 13일이 되기 전까지 Final을 신청할 수 있습니다. 원본별 만료 시각을 우선하며, 기간 확장을 지원하지 않는 브로커에서는 기존 7일을 적용합니다.

## 팀원용 최초 설치

1. Griptape Desktop과 Standard 라이브러리를 준비합니다. Desktop 0.31.0에는 SDK 0.106.0, Engine 0.113.0과 Editor 0.132.0이 포함됩니다.
2. Griptape에서 HMB Git 라이브러리를 등록한 뒤 작업을 저장하고 Griptape를 완전히 종료·재시작합니다.
3. 재시작 후 통합 헤더, 연결 관리, 로동마트 및 ‘로동 작업 계속’ 이미지가 표시되는지 확인합니다. 운영 서버를 사용하는 기능에는 팀원 본인의 인증이 필요합니다.

## 팀 PC 업데이트 안내

설치된 HMB Git 라이브러리는 Griptape의 **Git Update/Override**로 갱신합니다. 현재 작업을 저장하고 갱신한 뒤 Griptape를 완전히 종료·재시작합니다. 기존 저장본을 열어 샷 바인딩과 이미지·비디오 연결을 확인합니다.

Griptape Desktop의 자동 업데이트 차단은 팀 PC에 Windows 정책을 적용한 뒤 작동합니다. GitHub에서 HMB 라이브러리를 업데이트하는 절차와 별개입니다.

1. 열려 있는 작업을 저장하고 Griptape Desktop을 완전히 종료합니다.
2. 관리자는 팀 PC에 [자동 업데이트 차단 스크립트](tools/Set-GriptapeUpdateHold.ps1)를 관리자 권한으로 배포합니다.
3. Griptape를 다시 실행해 시작 로그에 `app updates disabled`가 표시되는지 확인합니다.

자세한 배포 절차와 확인 범위는 [Griptape Desktop 업데이트 검증](docs/GRIPTAPE_UPGRADE_ROLLOUT.md)에 있습니다.
