# HMB 연결 삭제 보호 계약

이 문서는 현재 및 앞으로 추가하는 HMB 툴의 개발 계약이다. 연결된 툴의 삭제·초기화가 다른 샷의 입력, 바인딩, 설정, 결과를 먼저 지우지 않도록 mutation 전에 검사한다. 적용 대상은 등록된 노드의 `metadata.library == "HMB_GP_Production"`이며 클래스 이름 목록에 의존하지 않는다.

## 사용자 동작

- 실제 선 또는 유효한 REMOTE 바인딩이 있으면 source와 consumer 어느 쪽의 삭제도 차단하고 연결 상대를 알린다.
- 사용자가 선과 REMOTE 바인딩을 먼저 해제한 뒤 다시 삭제하면 허용한다. 삭제 요청이 자동으로 연결을 끊어서는 안 된다.
- 연결이 없는 Only 툴은 삭제할 수 있다. Only로 표시되어도 실제 native 선이 남아 있으면 선 연결로 보호한다.
- 차단·조회 실패는 기존 노드, 선, 샷 UUID, 입력, 설정, 결과, Task ID, 미디어를 변경하지 않는다.
- 그룹·flow 일괄 삭제는 연결된 자식이 있는지 전체를 먼저 검사한다. 첫 자식을 삭제한 다음 다음 자식에서 차단하는 방식은 허용하지 않는다.
- 현재 공통 guard는 native Reset에도 같은 사전 검사를 적용한다. 정상 워크플로 New/Close/Open의 메모리 해제는 기존 저장·닫기 절차를 거치는 전용 전환 경로를 사용하며, 일반 Delete/Clear의 우회 수단으로 제공하지 않는다.

자동으로 도착한 catalog를 REMOTE 바인딩으로 보호한다면 사용자가 명시적으로 해제할 수 있어야 한다. 해제 직후 자동 발견이 다시 바인딩하면 해제가 아니다. 단순 catalog 광고인지 실제 수락한 작업 관계인지 구분하고, 해제 경로가 없는 자동 구독을 추가하여 두 툴 모두 영구 삭제 불가 상태로 만들지 않는다. 이는 배포 전 사용성 검사 항목이다.

## 공통 연결 관리 API

현재 구현의 공통 backend는 `_hmb_connection_management.py`다. HMB native 헤더의 연결 관리에서 현재 툴의 visible wire 및 REMOTE 관계를 조회하고 해제·다시 연결한다. 새 HMB 타입도 library metadata와 dependency hook으로 같은 API를 사용한다.

| 요청 | 필드 | 결과 |
|---|---|---|
| `HMBGetNodeConnectionsRequest` | `node_name` | read-only 현재 목록 |
| `HMBManageNodeConnectionsRequest` | `node_name`, `operation` (`disconnect` / `reconnect` / `forget_missing`), `expected_state_token` | 검증된 상태 변경 후 새 목록 |

성공 DTO는 `node_name`, `detached`, `state_token`, `can_disconnect`, `can_reconnect`, `connections`, `details`를 제공한다. 각 연결 행은 `kind` (`wire` / `remote`), `peer_name`, source/target node·parameter 이름과 `shots` 배열을 가진다. 실패는 `result_details`를 표시하며 이전 조회의 token으로 상태를 변경하지 않는다. token은 현재 workflow/flow, exact 객체, 현재 연결과 보존 recipe를 묶는 불투명 값이다. UI는 값을 해석하거나 재구성하지 않는다.

`can_forget_missing`, `missing_count`, `forget_missing_reason`은 삭제된 원본의 기록 정리 가능 여부·개수·사유를 제공한다. UI의 **삭제된 연결 기록 정리**는 `forget_missing`을 호출한다. 설명은 “삭제된 상대의 복구 기록을 정리합니다. 이후 기존 샷 설정에 따른 연결 검색이 다시 허용됩니다. 입력·결과는 유지되며 새 실행은 하지 않습니다.”로 표시한다. retained UUID owner/source/target가 완전히 사라진 기록만 정리한다. 살아 있는 원본의 일시 해제, 다른 flow로 이동한 원본, 동일 UUID가 여러 개 있는 경우는 정리하지 않는다. 이 동작도 잠금·실행 중·context·token 검사와 metadata rollback을 거치며 즉시 reconcile/새 실행을 시작하지 않는다.

조회는 node identity를 생성하지 않고 현재 상태를 변경하지 않는다. 최초 해제 transaction이 `metadata.hmb_connection_identity_v1`에 persistent UUID를 저장하고, `metadata.hmb_connection_management_v1`에 detached 상태와 원본 연결 recipe를 저장한다. 양 endpoint의 `metadata.hmb_connection_fences_v1`가 해당 관계의 자동 재바인딩을 억제한다. 이 metadata는 native workflow 저장·재오픈을 통해 유지된다.

해제는 선택한 툴과 접한 관계만 중단한다. 다른 peer 사이의 연결은 유지한다. source가 삭제되어도 consumer에 남은 fence는 다른 동일 이름·channel source를 자동으로 대신 연결하지 않는다. 기존 5샷의 입력·프롬프트·설정·결과·Task ID는 연결 recipe와 별도로 그대로 유지한다. 연결 해제 중인 툴과 중단된 upstream을 가진 consumer의 실행은 재연결 전까지 실패를 반환하며 새 렌더를 시작하지 않는다.

재연결은 persistent original node UUID의 유일성, 같은 flow, 원본 shot UUID 및 사용 중인 포트를 먼저 확인한다. 완료 LUT origin과 ImageBash workspace도 기록된 원본 identity를 검증한다. 같은 이름의 다른 객체, 복제 UUID, 삭제된 샷, 다른 flow, occupied input/control output을 임의로 대체하지 않는다. 잠금과 실행 중 상태는 조회를 허용하고 변경을 차단한다.

냉재오픈 시 해제된 manager의 live catalog는 아직 비어 있을 수 있다. 이 경우 수락 당시 recipe의 요청 샷 UUID와 **현재 원본 Asset의 persistent node UUID·publisher instance 및 live catalog**를 함께 검증한다. 저장된 표시 catalog만으로 실행 권위를 되살리지 않는다. 정상 재연결 후 정식 hydration reconciliation을 예약한다. 원본 객체의 이름만 바뀌었으면 persistent UUID로 현재 이름을 해석할 수 있다.

변경은 공식 native metadata/connection 요청을 사용하고 성공 결과를 broadcast하여 dirty 상태와 선 UI를 갱신한다. 짧은 동기 transaction 동안 exact endpoint의 callback·입력 삭제·상태 무효화만 보류한다. 다른 thread/context의 callback은 원래 함수를 호출한다. 부분 실패는 이 transaction의 변경만 롤백한다. context나 exact 객체가 교체되면 오래된 이름으로 새 그래프에 롤백 요청을 보내지 않는다.

SDK metadata는 merge-only다. 실패 transaction이 처음 추가한 키를 backend에서만 삭제하면 editor의 오래된 metadata spread가 fence를 다시 저장할 수 있다. 따라서 rollback은 원래 없었던 관리 키에 `hmb_connection_identity_v1=""`, `hmb_connection_management_v1={}`, `hmb_connection_fences_v1=[]`의 무효한 중립값을 공식 broadcast하고 backend에도 같은 값을 유지한다. 회귀에서는 이 중립값과 키 부재를 의미상 동등하게 취급하며, 원래 있던 metadata와 입력·결과는 exact 비교한다.

## 판정 순서와 권위

1. 현재 NodeManager가 반환한 exact Python 객체와 parent flow를 한 번 수집한다. 같은 이름의 이전 객체, 삭제 중인 객체, 다른 flow의 객체는 REMOTE 상대가 아니다.
2. native `ListConnectionsForNodeRequest(include_internal=True)`의 incoming/outgoing 양쪽을 확인한다. 숨김 선과 내부 선도 실제 선이다. 외부 라이브러리 노드에 연결된 HMB 툴도 보호한다.
3. 선 없는 REMOTE 관계는 현재 라우터가 선택하는 exact owner만 사용한다. channel·shot UUID와 현재 수락한 publisher 증거를 검사한다. 동일한 이름·샷 번호·프로젝트·파일 경로만으로 관계를 만들지 않는다.
4. Prompt·Agent·Finish manager는 현재 열린 페이지 대신 최대 5개 전체 subscription을 검사한다. 페이지 변경은 연결 해제가 아니다.
5. 새로운 비선형 REMOTE 툴은 아래 dependency hook으로 현재 상대 객체를 선언한다. 현재 source 후보 목록이나 과거 표시용 catalog는 바인딩 선언이 아니다.

판정 중에는 reconcile, 자동 bind/unbind, 상태 publish, setter, 미디어 resolve/probe, 파일 조회, 이미지 decode, 네트워크, provider, 렌더를 실행하지 않는다. 읽을 수 없으면 삭제 실패를 반환한다. 정상적으로 연결이 없는 것과 연결 상태를 확인하지 못한 것을 구분한다.

## 현재 샷 라우팅 관계

공통 구현은 `_hmb_deletion_guard.py`이며 실제 소유자 규칙은 `_hmb_shot_routing.py`의 `_single`, `_manager_prompt_for_agent`, `_agent_for_target`를 재사용한다. 공개 `resolve_shot_*_owner`는 단일 소비자용으로 flow를 재수집하므로 배치 삭제 검사에서는 이미 수집한 subscription을 재사용한다.

| 관계 | 선 없는 경우의 판정 | 보호 근거가 아닌 것 |
|---|---|---|
| ImageAsset → Picker | 유일한 ImageAsset channel authority와 Picker의 현재 수락한 같은 channel | Picker의 UI Only 글자만으로 publisher 역할을 지우지 않음 |
| ImageAsset → Prompt / Agent / Finish / Seedance / LUT | 활성 단일 subscription 또는 manager 전체 행 중 current authority에 속하는 행. 알려진 publisher/channel 불일치와 catalog에 없는 UUID는 제외 | 선택 가능한 dropdown 목록, 과거 샷 이름 |
| Picker → Prompt / Seedance | 같은 channel의 유일한 유효 Picker와 실제 대상 subscription | 같은 프로젝트, 다른 channel |
| standalone Picker → Seedance / LUT | 활성 ImageAsset이 없는 flow에서 유일 standalone Picker의 실제 workspace UUID에 속하는 대상 | standalone Picker가 있다는 이유만으로 모든 툴에 연결 |
| Prompt → Agent | legacy는 정확한 단일 Prompt owner, manager는 `_manager_prompt_for_agent`가 선택한 한 Prompt manager | 여러 후보 중 이름순 첫 노드 |
| Agent → Seedance | `_agent_for_target`가 선택한 owner와 정확한 해당 샷 행. 중복 manager는 기존 exact native edge 규칙을 따름 | Agent의 현재 열린 페이지만 비교 |
| Finish → Seedance | `_single`이 선택한 exact 샷 owner 또는 manager의 해당 샷 행 | 다른 샷에서 선택한 Finish 설정 |
| Generator → LUT | 실제 native source 선. 선 없는 보완은 LUT가 이미 수락한 origin과 Generator의 이미 존재하는 완료 receipt가 exact 일치할 때만 | 완료 파일을 후보로 발견했거나 같은 shot 이름인 것 |
| ImageAsset → ImageBash | native parent image-list 선과 context 선. 일반 Shot 1~5와 별도 workspace 계약 | source dropdown, target metadata에 남은 이름만 있는 상태 |
| Image Generation | 실제 native 입력·출력 선 또는 앞으로 명시 구현할 dependency hook | 모델 선택, 브로커 주소, 출력 파일 |

현재 라우터는 ImageAsset 없는 standalone Picker catalog를 Seedance/LUT에만 제공한다. Prompt·Agent·Finish는 ImageAsset을 authority로 사용한다. 또한 Finish의 과거 Picker 입력 의존성은 폐기되었다. 따라서 Picker → Finish, standalone Picker → Prompt/Agent/Finish를 가상 연결로 추가하지 않는다. 과거 워크플로에 실제 선이 남은 경우에는 그 선 자체가 보호 근거다.

Seedance의 실제 `only` 또는 `waiting` mode는 자동 upstream 관계에서 제외한다. 프로젝트 선택·Task ID·중단 전 요청 identity만으로 현재 REMOTE 바인딩을 추정하지 않는다. 다만 완료 결과의 origin은 Generator의 현재 선택 페이지와 별개이므로, LUT가 수락한 기존 완료 결과는 cached origin으로 판단한다.

## 새 툴의 비선형 REMOTE hook

```python
def _hmb_deletion_dependencies(self):
    # 현재 수락한 바인딩만 읽는다. 후보 검색·재연결을 실행하지 않는다.
    peer = self._accepted_live_source
    return (peer,) if self._binding_is_current and peer is not None else ()
```

`_hmb_deletion_dependencies()` 반환값은 `list`, `tuple`, `set`, `frozenset` 중 하나이며 그 원소는 실제 현재 등록 객체다. 문자열, 노드 이름 DTO, subscriber가 보낸 임의 ID를 반환하지 않는다. hook은 source/consumer 중 한쪽에서 선언하면 공통 guard가 삭제 검사를 대칭 적용한다.

구현 시 다음을 보장한다.

- explicit bind 성공 뒤에만 accepted peer를 확정하고 explicit unbind 성공 뒤에는 비운다. 요청 중·실패·롤백 상태를 새 binding으로 발표하지 않는다.
- 대상 객체가 NodeManager 및 같은 flow에서 exact 객체로 살아 있는지 확인한다. 같은 이름으로 재생성된 객체는 자동 승계하지 않는다.
- 비동기 callback은 source instance token, workspace/shot UUID, revision 등 기존 바인딩 계약으로 fence한다. 예전 callback이 새 연결을 해제하거나 새 객체를 보호 대상으로 만들지 않는다.
- 복원된 display DTO만으로 실행 권위를 되살리지 않는다. 정식 native wire 또는 기존의 수락·복원 검증이 끝난 연결 상태를 사용한다.
- 선을 이미 사용하는 툴은 별도 hook을 억지로 추가할 필요가 없다. 숨긴 선도 native 연결 목록에 포함된다.
- 한 target에 동일 클래스 source 여러 개를 서로 다른 역할로 연결하는 새 비선형 툴은 역할별 native typed port를 사용한다. 현재 peer-only hook에는 role 필드가 없어, 같은 `source_kind`의 여러 가상 관계를 서로 독립적으로 해제·복원하는 계약까지 표현하지 못한다. 새 툴에서 이 모양이 필요하면 먼저 역할·port별 관계 계약과 회귀를 추가하며, 단순 클래스 이름 matching으로 독립 관계를 합치지 않는다.
- hook은 현재 metadata만 읽고 상태를 변경하지 않는다. 반환 계약 오류는 공통 guard가 실패로 처리한다.

## UI와 host의 순서

Editor는 edge/node 일괄 삭제 전에 `HMBCheckNodeDeletionRequest(node_names=[...])`로 검사할 수 있다. `can_delete`가 false이거나 요청이 실패하면 edge 삭제를 시작하지 않는다. 성공 응답이 나왔더라도 실제 native mutation 직전의 공통 guard를 제거하지 않는다. 검사 이후 연결이 추가되는 race를 마지막 host guard가 차단해야 한다.

기존 disconnect·Only 전환·bind 교체는 해당 툴의 정식 계약을 따른다. 삭제 guard에서 연결을 정리하거나 재시도, 출력 무효화, 파일 삭제를 대신 실행하지 않는다. 정상적인 화면 전환의 내부 teardown 허가는 특정 engine/request 범위에 한정하고 다음 독립 Delete/Clear 요청에 남지 않아야 한다.

## 추가 노드의 필수 회귀

| 검사 | 기대 결과 |
|---|---|
| 선 없는 새 Only, 명시 unbind 완료 | 삭제 허용 |
| native incoming / outgoing / hidden / internal / 외부 노드와의 선 | source와 consumer HMB 삭제 모두 차단 |
| remote-only exact owner | 두 방향 삭제 차단, 입력·결과·선 변경 0 |
| inactive Shot 5 manager 행과 Shot 5 consumer | 현재 페이지가 Shot 1이어도 보호 |
| same name 새 객체, 다른 flow의 동일 UUID, 삭제된 객체 | 가상 관계로 과보호하지 않음 |
| 외국 publisher/channel, 없는 shot UUID, 중복 owner | 임의 owner 추측 금지; 실제 선은 계속 보호 |
| Seedance Only / waiting, catalog 후보만 존재 | 선이 없으면 자동 관계로 보호하지 않음 |
| 정확한 LUT 완료 origin / 다른 task·instance·revision·path | exact origin만 보완 보호, 파일 probe와 restore setter 호출 0 |
| explicit disconnect 후 동일 source 재연결 / 다른 source 연결 | 옛 객체·callback의 관계가 남지 않음 |
| 저장·cold reopen | 수락 전 display catalog를 권위로 쓰지 않고 정식 복원 후 보호 |
| 혼합 그룹/flow 삭제, 연결 노드가 목록 뒤쪽 | 앞쪽 미연결 노드도 먼저 삭제되지 않음 |
| 잘못된 hook 반환값, 조회 실패 | 실패 안내, 원래 그래프·샷·Task·미디어 보존 |
| 정상 New/Close/Open 뒤 직접 Clear/Delete | 전환 허가가 새 독립 요청에 유출되지 않음 |

이 문서의 계약 검사는 source/SDK 회귀 증거이며 실제 앱의 메뉴·키보드·그룹 삭제 동작 검수와 구분해 보고한다. 과금 생성이나 운영 서버 변경은 삭제 보호 검증에 필요하지 않다.
