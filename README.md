# HMB GP Production

## 팀 PC 업데이트 안내

팀 배포 버전은 **Team v0.8.59**입니다. HMB 라이브러리는 Griptape의 **Git Update/Override**로 갱신합니다.

Griptape Desktop의 자동 업데이트 차단은 팀 PC에 Windows 정책을 적용한 뒤 작동합니다. GitHub에서 HMB 라이브러리를 업데이트하는 절차와 별개입니다.

1. 열려 있는 작업을 저장하고 Griptape Desktop을 완전히 종료합니다.
2. 관리자는 팀 PC에 [자동 업데이트 차단 스크립트](tools/Set-GriptapeUpdateHold.ps1)를 관리자 권한으로 배포합니다.
3. Griptape를 다시 실행해 시작 로그에 `app updates disabled`가 표시되는지 확인합니다.

자세한 배포 절차와 확인 범위는 [Griptape Desktop 업데이트 검증](docs/GRIPTAPE_UPGRADE_ROLLOUT.md)에 있습니다.
