# HMB GP Production

Team **v0.8.71**은 Local **v0.8.72**에서 검증한 기능과 UI 자산을 함께 제공합니다. 이번 변경 및 검증 범위는 [릴리스 안내](docs/HMB_TEAM_V0_8_71.md)를 확인하세요.

## Team v0.8.71 최초 설치

1. Griptape Desktop과 Standard 라이브러리를 준비합니다. 이 패키지는 SDK 0.104.0과 Editor 0.130.0 조합에서 검증했습니다.
2. Griptape에서 HMB Git 라이브러리를 등록한 뒤 작업을 저장하고 Griptape를 완전히 종료·재시작합니다. 설치 ZIP을 사용하는 경우 Griptape를 종료한 뒤 ZIP을 풀고 그 안의 `Install_HMB_GP_Production.ps1`을 실행합니다.
3. 재시작 후 통합 헤더, 연결 관리, 로동마트 및 ‘로동 작업 계속’ 이미지가 표시되는지 확인합니다. 운영 서버를 사용하는 기능에는 팀원 본인의 인증이 필요합니다.

## 팀 PC 업데이트 안내

설치된 HMB Git 라이브러리는 Griptape의 **Git Update/Override**로 갱신합니다. 현재 작업을 저장하고 갱신한 뒤 Griptape를 완전히 종료·재시작합니다. 기존 저장본을 열어 샷 바인딩과 이미지·비디오 연결을 확인합니다. ZIP으로 갱신할 때 설치기는 기존 라이브러리를 롤백 위치에 보관한 뒤 검증된 파일을 적용합니다.

Griptape Desktop의 자동 업데이트 차단은 팀 PC에 Windows 정책을 적용한 뒤 작동합니다. GitHub에서 HMB 라이브러리를 업데이트하는 절차와 별개입니다.

1. 열려 있는 작업을 저장하고 Griptape Desktop을 완전히 종료합니다.
2. 관리자는 팀 PC에 [자동 업데이트 차단 스크립트](tools/Set-GriptapeUpdateHold.ps1)를 관리자 권한으로 배포합니다.
3. Griptape를 다시 실행해 시작 로그에 `app updates disabled`가 표시되는지 확인합니다.

자세한 배포 절차와 확인 범위는 [Griptape Desktop 업데이트 검증](docs/GRIPTAPE_UPGRADE_ROLLOUT.md)에 있습니다.
