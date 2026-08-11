# HMB Agent 전용 정책 공유 운영 런북

이 문서는 `FIN-RCOMP7.funnyflux.local`의 물리 경로 `D:\agent`에 이미 존재하는 서명 정책을 전용 숨김 공유로 읽게 하는 준비 절차다. 이 저장소의 스크립트는 자동 실행되지 않으며, 서버 변경은 승인된 관리자가 서버 콘솔의 상승된 Windows PowerShell에서 명시적으로 실행할 때만 발생한다.

고정 경계는 다음과 같다.

| 항목 | 고정값 |
|---|---|
| 서버 | `FIN-RCOMP7.funnyflux.local` (`FIN-RCOMP7`) |
| 실제 live 파일 | `D:\agent\hmb_agent_core.dat` |
| 관리자 전용 백업 | `D:\agent\backup` |
| 런타임 UNC | `\\FIN-RCOMP7.funnyflux.local\HMB_AgentPolicy$\hmb_agent_core.dat` |
| SMB 설정 | 공유별 암호화, 캐시 없음, ABE 사용 |

`hmb_agent_core.dat`와 정책 원문은 GitHub 배포 패키지에 넣지 않는다. 관리 스크립트도 정책 내용을 읽어 화면에 출력하지 않고 승인 SHA-256, 버전 및 contract SHA-256만 출력한다.

## 1. 실행 전 승인 자료

다음 값을 보안 담당자에게서 받아 기록한다. 스크립트에는 ACL identity 기본값이 없으며 이름을 추측하지 않는다.

- `Readers`: 런타임이 사용하는 승인된 전용 보안 주체. 가능하면 사람 계정이 아닌 Agent 서비스 보안그룹 또는 서비스 계정으로 제한한다.
- `PolicyAdmins`: Reader와 멤버가 겹치지 않는 전용 정책 관리자 보안그룹.
- 현재 live 파일의 승인 SHA-256.
- 배포할 새 파일의 승인 SHA-256과 그 파일을 검증할 동일 릴리스의 `LibraryRoot`.

`Everyone`, `Authenticated Users`, `BUILTIN\Users`, `SYSTEM`, 로컬 Administrators는 Reader/PolicyAdmins 매개변수로 사용할 수 없다. 스크립트는 전용 PolicyAdmins 외에도 `SYSTEM`과 로컬 Administrators에만 관리 권한을 유지한다.

중요: Reader가 파일을 읽을 수 있으면 그 Reader는 서명·압축된 `.dat` 바이트를 복사할 수도 있다. 일반 사용자에게 절대 복사를 허용할 수 없다면 사용자 그룹을 Readers로 지정하지 말고 격리된 Agent 서비스 identity만 승인해야 한다. SMB 읽기 권한만으로 “읽되 복사하지 못함”을 구현할 수는 없다.

## 2. 현재 상태의 사전 조건

관리 스크립트는 `D:\agent`에 다음 두 항목 외의 파일이나 폴더가 있으면 중단한다.

- `hmb_agent_core.dat`
- `backup` (없으면 최초 구성 중 생성)

`D:\agent`, live 파일, `backup`, 백업 파일의 재분석 지점과 alternate data stream을 거부한다. `D$` 같은 관리자 특수 공유는 허용하지만, `D:\agent`의 상위 또는 하위 경로와 겹치는 다른 일반 SMB 공유가 있으면 중단한다. 따라서 스크립트 자체와 서명 전 원본은 `D:\agent` 밖의 관리자 전용 폴더에 둔다.

서버는 `funnyflux.local` 도메인 가입 상태여야 하며 SMB2 이상과 `RejectUnencryptedAccess=True`가 유지되어야 한다. 서버 전역 `EncryptData=False`여도 괜찮지만, `HMB_AgentPolicy$` 공유 자체의 `EncryptData=True`는 필수다.

먼저 스크립트의 구문과 정적 경계를 검토한다. 이 명령은 서버를 변경하지 않는다.

```powershell
powershell -NoProfile -File C:\HMB_GP_Production\resources\tests\HMB_Agent_Policy_Admin_Scripts_Static_Regression.ps1
```

## 3. 전용 공유 구성

서버 콘솔의 관리자 전용 작업 폴더에서 다음을 먼저 `-WhatIf`로 실행한다. 자리표시자는 승인받은 실제 값으로만 교체한다.

```powershell
.\Configure_HMB_Agent_Policy_Share.ps1 `
  -Readers "<승인된 Reader identity>" `
  -PolicyAdmins "<승인된 PolicyAdmins identity>" `
  -ExpectedSha256 "<현재 live의 승인 SHA-256 64자리>" `
  -LibraryRoot "<현재 런타임과 동일한 HMB_GP_Production root>" `
  -WhatIf
```

검토 후 별도 실행 승인이 있을 때만 `-WhatIf`를 제거한다. 스크립트는 다음을 하나의 구성 작업으로 적용하고 다시 검사한다.

- `D:\agent`: Reader는 폴더 통과/열거와 live 읽기만 가능.
- `D:\agent\hmb_agent_core.dat`: Reader `ReadAndExecute`, 관리자 `FullControl`.
- `D:\agent\backup` 및 내부 파일: Reader ACE 없음, 관리자만 `FullControl`.
- `HMB_AgentPolicy$`: Reader `Read`, 관리자 `Full`, `EncryptData=True`, `CachingMode=None`, `FolderEnumerationMode=AccessBased`.

구성 도중 검증이 실패하면 새 공유를 제거하고 변경 전 ACL의 SDDL을 복원한다. 기존 live 파일이나 백업 파일은 삭제하지 않는다. 복원이 완전하지 않으면 스크립트가 그 사실을 오류로 명시하므로 즉시 보안 관리자에게 전달한다.

성공한 공유 구성을 운영상 되돌려야 할 때는 다음 명령을 먼저 `-WhatIf`로 검토한다. 이 안전 롤백은 SMB 공유만 제거하고, hardened NTFS ACL과 live/backup 파일을 그대로 보존한다.

```powershell
.\Disable_HMB_Agent_Policy_Share.ps1 `
  -Readers "<승인된 Reader identity>" `
  -PolicyAdmins "<승인된 PolicyAdmins identity>" `
  -ExpectedLiveSha256 "<현재 live의 승인 SHA-256 64자리>" `
  -WhatIf
```

## 4. 서버 측 검증

서버 관리자 PowerShell에서 다음을 실행한다.

```powershell
.\Test_HMB_Agent_Policy_Share.ps1 `
  -Readers "<승인된 Reader identity>" `
  -PolicyAdmins "<승인된 PolicyAdmins identity>" `
  -ExpectedSha256 "<현재 live의 승인 SHA-256 64자리>" `
  -LibraryRoot "<현재 런타임과 동일한 HMB_GP_Production root>"
```

필수 결과는 `SERVER_VERIFY=PASS`, `BACKUP_ACCESS=ADMIN_ONLY`, `LIVE_ACCESS=READER_READ_ONLY`, `SHARE_ENCRYPTION=True`, `CACHING=None`, `ABE=AccessBased`다. 검증기는 현재 `_hmb_common.py`의 고정 공개키와 알고리즘, 엄격한 envelope/payload v3 스키마, payload 자체 SHA-256, 고정 Prompt/Agent contract, 정확한 Behavior 1/2의 4+4 구조 및 RSA 서명을 확인하며 정책 본문은 출력하지 않는다. 서명된 정책 버전과 policy/binding SHA-256은 감사 identity이며 특정 파일 바이트나 특정 정책 revision을 코드에 고정하는 허용 조건이 아니다.

## 5. 클라이언트 Hardened UNC 정책

현재 클라이언트의 Hardened UNC 항목이 0개이면 아직 활성화 준비가 끝난 것이 아니다. 도메인 GPO로 정확히 다음 항목을 배포한다. IP, NetBIOS 별칭, `D$` 또는 와일드카드 경로를 추가하지 않는다.

| 값 이름 | 값 데이터 |
|---|---|
| `\\FIN-RCOMP7.funnyflux.local\HMB_AgentPolicy$` | `RequireMutualAuthentication=1,RequireIntegrity=1,RequirePrivacy=1` |

GPO 위치는 `컴퓨터 구성 > 관리 템플릿 > 네트워크 > 네트워크 공급자 > 강화된 UNC 경로(Hardened UNC Paths)`다. 이 변경은 도메인 관리자 승인을 거쳐야 하며, 로컬 임시 레지스트리 값을 운영 대체 수단으로 사용하지 않는다.

GPO 적용 후 PolicyAdmins/Administrators에 속하지 않은 실제 Reader 세션에서 다음을 실행한다.

```powershell
& "<관리자가 별도로 전달한 Test_HMB_Agent_Policy_Reader.ps1 경로>" `
  -Readers "<승인된 Reader identity>" `
  -PolicyAdmins "<승인된 PolicyAdmins identity>" `
  -ExpectedSha256 "<현재 live의 승인 SHA-256 64자리>" `
  -LibraryRoot "C:\HMB_GP_Production"
```

필수 결과는 다음과 같다.

- `CLIENT_HARDENED_UNC=PASS`
- `READER_READ=PASS`
- `READER_WRITE_OPEN=PASS (access denied)`
- `ABE=PASS BACKUP_ISOLATION=PASS`
- `SMB_TRANSPORT=PASS ... ENCRYPTED=True`
- `READER_LOADER=PASS`
- `READER_VERIFY=PASS`

Reader 검증은 live 파일에 쓰기·이름 변경·삭제를 수행하지 않는다. 쓰기 권한은 파일 내용을 변경하지 않는 write-handle open 요청이 거부되는지로 확인한다.

## 6. 정책의 원자적 배포

새 정책은 먼저 현재 애플리케이션 코드와 함께 오프라인 검증되어야 한다. 서버 관리자 전용 staging 경로는 `D:\agent` 밖에 둔다. 다음 명령도 먼저 `-WhatIf`로 검토하고 별도 승인 후에만 실행한다.

```powershell
.\Deploy_HMB_Agent_Policy_Atomic.ps1 `
  -SourcePolicy "<D:\agent 밖의 관리자 전용 새 서명 .dat>" `
  -ExpectedSourceSha256 "<새 승인 SHA-256>" `
  -ExpectedCurrentSha256 "<현재 live 승인 SHA-256>" `
  -Readers "<승인된 Reader identity>" `
  -PolicyAdmins "<승인된 PolicyAdmins identity>" `
  -LibraryRoot "<고정 공개키·스키마·contract가 호환되는 HMB_GP_Production root>" `
  -WhatIf
```

`ExpectedSourceSha256`와 `ExpectedCurrentSha256`는 각 교체 작업에서 승인한 후보와 직전 live 바이트를 정확히 확인하는 변경 승인/경쟁 방지 값이다. 코드에 내장된 정책 파일 pin이 아니므로, Master가 작은 수정 후 같은 신뢰 키로 별도 서명한 호환 `.dat`의 실제 SHA-256을 `ExpectedSourceSha256`로 주면 패키지 재배포 없이 검증·교체할 수 있다. 파일 자체는 signed+compressed 형식이며 암호화 형식은 아니다.

실행 시 순서는 다음과 같다.

1. 새 파일의 작업별 승인 SHA-256, RSA 서명, 엄격한 스키마/self-hash/4+4 구조 및 고정 contract 호환성을 변경 전에 검증한다.
2. 현재 live를 `D:\agent\backup`에 flush하여 복사하고 SHA-256을 재검증한다.
3. 새 파일을 같은 NTFS 볼륨의 관리자 전용 backup 아래에 stage하고 다시 검증한다.
4. live가 예상 이전 SHA-256 그대로인지 재확인한다.
5. `[System.IO.File]::Replace`로 live 이름을 원자적으로 전환한다.
6. live 경로에서 서명·SHA·ACL·SMB 경계를 다시 검증한다.

전환 후 검증이 실패하면 보관한 이전 바이트를 같은 방식으로 원자 복원한다. 성공 출력의 `BACKUP_PATH`, 이전/새 SHA-256을 변경 기록에 보관한다. 소스 staging 파일은 승인된 절차로 제거하되 `D:\agent\backup`의 검증된 백업은 지우지 않는다.

## 7. 원자적 롤백

롤백할 백업이 현재 코드의 신뢰 키·v3 스키마·고정 contract·4+4 구조와 호환되는지 먼저 검증한다. 호환된다면 서명된 버전 metadata나 policy/binding SHA-256이 현재 live와 달라도 같은 `TargetLibraryRoot`로 검증할 수 있다. contract 또는 스키마가 다른 백업에는 그 contract를 지원하는 별도 코드 릴리스가 필요하며, 서로 맞지 않는 동안 Agent는 fail-closed 상태가 정상이다.

```powershell
.\Rollback_HMB_Agent_Policy_Atomic.ps1 `
  -BackupPolicy "D:\agent\backup\<검증된 백업 파일명>.dat" `
  -ExpectedBackupSha256 "<복원 대상 승인 SHA-256>" `
  -ExpectedCurrentSha256 "<현재 live 승인 SHA-256>" `
  -Readers "<승인된 Reader identity>" `
  -PolicyAdmins "<승인된 PolicyAdmins identity>" `
  -TargetLibraryRoot "<백업의 신뢰 키·스키마·contract와 호환되는 코드 root>" `
  -WhatIf
```

승인 후 `-WhatIf`를 제거한다. 롤백 스크립트는 현재 live의 안전 백업을 먼저 추가하고, 선택한 백업을 서명 검증한 뒤 원자 교체한다. 롤백 후 검증 실패 시 롤백 직전 live 바이트를 자동으로 원자 복원한다.

## 8. 운영 금지 사항과 기록

- 정책 파일이나 원문에 `Get-Content`, `type`, 편집기 미리보기 또는 로그 수집기를 사용하지 않는다.
- `D:\agent`를 다른 일반 공유의 하위 경로로 노출하지 않는다.
- `backup`에 Reader 권한을 추가하거나 offline caching을 켜지 않는다.
- IP 기반 UNC, `D$`, 환경변수 또는 로컬 패키지 파일로 Agent loader를 우회하지 않는다.
- Reader/PolicyAdmins 멤버 변경, GPO 적용, 공유 생성, 배포, 롤백은 각각 승인 및 감사 기록을 남긴다.
- 각 배포 후 서버 검증과 실제 Reader 검증을 다시 수행하고 Griptape를 완전히 재시작한 뒤 HMB Prompt→Agent 연결을 확인한다.
