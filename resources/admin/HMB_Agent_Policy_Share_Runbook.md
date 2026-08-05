# HMB Agent 전용 정책 공유 설정

이 절차는 `FIN-RCOMP1` 서버 콘솔의 관리자 PowerShell과, PolicyAdmins/로컬 Administrators에 속하지 않은 일반 Reader Windows 계정을 각각 사용합니다. 사용량 원장이나 다른 광범위 공유의 하위 폴더를 정책 저장소로 사용하지 마십시오.

## 1. 선택 사용자 그룹 준비

기존 AD 그룹을 사용할 수 있습니다. 서버 로컬 그룹을 새로 만드는 경우 `FIN-RCOMP1`의 관리자 PowerShell에서 다음을 실행하고 실제 계정을 추가합니다.

```powershell
New-LocalGroup -Name "HMB_AgentPolicy_Readers" -Description "HMB Agent policy read-only clients"
New-LocalGroup -Name "HMB_AgentPolicy_Admins" -Description "HMB Agent policy administrators"

Add-LocalGroupMember -Group "HMB_AgentPolicy_Readers" -Member "DOMAIN\selected-user"
Add-LocalGroupMember -Group "HMB_AgentPolicy_Admins" -Member "DOMAIN\selected-admin"
```

Reader와 PolicyAdmins 멤버를 겹치게 넣지 마십시오. 추가 사용자는 `Add-LocalGroupMember`만 반복합니다.

## 2. 서버 전용 공유 생성

세 관리자 스크립트를 `FIN-RCOMP1`의 관리자만 쓸 수 있는 로컬 폴더로 복사합니다. 관리자 PowerShell에서 해당 폴더로 이동한 뒤 아래 명령을 실행합니다. `SecureContainer`는 아직 존재하지 않는 로컬 경로여야 하며 다른 SMB 공유의 backing tree 밖이어야 합니다.

```powershell
.\Configure_HMB_Agent_Policy_Share.ps1 `
  -SecureContainer "D:\HMB_AgentPolicy_Secure" `
  -Readers "FIN-RCOMP1\HMB_AgentPolicy_Readers" `
  -PolicyAdmins "FIN-RCOMP1\HMB_AgentPolicy_Admins" `
  -SourcePolicy "<현재 임시 정책 파일의 UNC>"
```

스크립트는 보호된 NTFS ACL, Reader SMB Read, 관리자 SMB Full, SMB 암호화, 오프라인 캐시 금지를 적용하고 실제 ACE를 재검증합니다. 출력의 `POLICY_UNC`와 `SHA256`을 기록합니다.

## 3. 일반 Reader 계정 검증

선택된 일반 Reader 계정으로 Windows에 로그인합니다. 설치된 라이브러리 root가 `C:\HMB_GP_Production`인 경우 다음과 같이 실행합니다. SHA-256은 2단계 출력값으로 교체합니다.

```powershell
& "\\FIN-RCOMP1\HMB_AgentPolicy$\Test_HMB_Agent_Policy_Share.ps1" `
  -PolicyUNC "\\FIN-RCOMP1\HMB_AgentPolicy$\hmb_agent_core.dat" `
  -ExpectedSha256 "<2단계 SHA256>" `
  -LibraryRoot "C:\HMB_GP_Production" `
  -PolicyAdmins "FIN-RCOMP1\HMB_AgentPolicy_Admins"
```

필수 성공 출력은 `READ=PASS`, `CREATE=PASS (access denied)`, `RENAME=PASS (access denied)`, `DELETE=PASS (access denied)`, `LOADER=PASS SIGNATURE=VALID`입니다. 하나라도 없으면 환경변수를 영구 설정하지 않고 원인을 수정합니다. 모두 통과하면 스크립트가 현재 사용자의 `HMB_AGENT_POLICY_PATH`를 설정합니다. Griptape를 완전히 종료한 뒤 다시 시작합니다.

## 4. 런타임 재검증

새 PowerShell에서 다음을 실행합니다.

```powershell
python C:\HMB_GP_Production\resources\tests\HMB_Agent_Policy_Integration_Regression.py
python C:\HMB_GP_Production\resources\tests\HMB_Parent_Prompt_Agent_Contract_Regression.py
```

그 다음 Griptape에서 HMB Prompt 연결 Agent 1회와 일반 비-HMB Agent 1회를 실행합니다. HMB 연결은 정책 적용 상태로 성공해야 하고, 일반 Agent는 정책과 독립적으로 동작해야 합니다.

## 5. 임시 정책 사본 제거

3~4단계가 모두 통과한 뒤에만 `FIN-RCOMP1` 관리자 PowerShell에서 다음을 실행합니다. 이 단계는 기존 광범위 공유의 임시 정책 사본을 삭제하며, 전용 공유의 검증된 사본은 유지합니다.

```powershell
.\Finalize_HMB_Agent_Policy_Migration.ps1 `
  -LegacyPolicy "<기존 임시 정책 파일의 UNC>" `
  -PolicyUNC "\\FIN-RCOMP1\HMB_AgentPolicy$\hmb_agent_core.dat" `
  -ExpectedSha256 "<2단계 SHA256>" `
  -ReaderValidationPassed
```

정책 갱신은 PolicyAdmins가 전용 로컬 폴더의 파일을 검증된 새 서명 파일로 교체하는 방식으로 중앙 수행합니다. Reader에게는 파일 변경·이름변경·삭제 권한을 주지 않습니다.
