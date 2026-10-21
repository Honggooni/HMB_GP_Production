# My Box: Only 전용 개인 영상 작업공간

My Box는 샷 제작 전의 개인 소스 영상, Video Editing 및 Video Extension을 위한 Only 전용 영상 공간이다. 생성과 로컬 저장은 Griptape Generator에서 수행하고, 웹에서는 기존 제작리뷰의 **프로젝트 선택 목록 → My Box**에서 본인 영상을 확인한다. 별도 My Box 웹사이트와 웹 전용 생성기를 제공하지 않는다.

이 문서는 클라이언트와 서버의 기능 계약이다. 패키지에 코드가 포함되어 있어도 서버의 지원·활성화·계정 승인이 확인되기 전에는 생성 가능 상태로 간주하지 않는다. 배포 버전·실제 설치·서버 활성화 상태는 각각 검증한다.

## 범위와 권한

- Generator의 Only 모드에서 `Project (Only) → My Box`를 명시적으로 선택한다. 미선택을 My Box나 미분류로 자동 해석하지 않는다.
- 기존 Broker의 승인·활성 계정과 동일한 인증을 사용한다. 클라이언트에 개인 API 키를 입력하거나 새 계정을 만들지 않는다.
- 서버가 로그인 사용자로 소유권을 결정한다. 목록·상세·원본·미디어·다운로드·수정·Confirm·Keep·소스 재사용 모두 본인 범위를 유지한다.
- My Box는 제작 프로젝트가 아니다. ImageAsset, Picker, Prompt, Agent, Finish Look, Color LUT의 일반 프로젝트 목록과 정책 폴더에 추가하지 않는다. 일반 프로젝트 목록에 개인 공간 식별자를 등록하지 않는다.
- 생성 이미지는 개인 로컬 전용으로 유지한다. 이미지를 영상의 레퍼런스로 사용하는 것과 생성 이미지 결과를 웹에 게시하는 것은 구분한다.
- 샷에 바인딩된 제작 프로젝트·프롬프트·Agent·정책·결과·Task ID와 기존 사용 방식은 유지한다. Only 선택값이 샷 바인딩의 프로젝트 권위를 바꾸지 않는다.

## 웹 표시

제작리뷰 프로젝트 선택의 My Box는 **현재 로그인 사용자의 개인 영상 필터**다. UI 내부 식별자 `__my_box__`는 화면 전환에만 사용하며, production `project_id`, GP의 `only_project`, 정책 폴더 이름이나 생성 요청에 넣지 않는다. GP의 선택값은 정확한 문자열 `My Box`다.

웹은 기존 개인 API 결과를 같은 제작리뷰 카드·플레이어·다운로드 UI에 표시한다. 개인 영상을 일반 팀 제작리뷰 행으로 복사하지 않으며, API의 `publish_to_reviews=false` 계약을 유지한다. My Box에서 Confirm하거나 Keep해도 팀 공개·프로젝트 공유 권한으로 승격되지 않는다.

## 보관·Draft

| 항목 | 계약 |
| --- | --- |
| 기본 관리 기간 | 완료 시점을 기준으로 30일 관리 만료 예정일을 표시한다. `management_expires_at`은 접근 차단용 만료 토큰과 다르다. |
| 자동 정리 | `automatic_deletion_enabled=false`, `management_deadline_disables_media=false`를 유지한다. 30일 표시는 자동 삭제 작업이 켜졌다는 뜻이 아니다. |
| Keep | 본인 Keep 상태를 변경한다. Keep 시 관리 만료 예정일을 해제하며, 해제 시점부터 30일 관리 예정일을 다시 설정한다. 실제 정리 정책은 별도 서버 관리 범위다. |
| Confirm | 본인 개인 영상의 컨펌 상태다. 일반 팀 컨펌의 공개·공유 확장을 적용하지 않는다. |
| Draft Final | 원본 생성 시점 및 공급자 제한을 기준으로 최대 7일이다. 완료·Keep·30일 관리 기간으로 새 7일을 부여하지 않는다. |
| 480p 설정 | 반복 생성·재렌더·Final 후에도 Generator의 기존 480p 및 Draft 작성 설정을 보존한다. Final 제출 시에만 원본 Task에 묶인 임시 1080p 요청을 사용한다. |
| 중복 방지 | 이미 예약·실행·완료·실패한 Final child가 있으면 그 Task를 조회한다. 불확정 결과를 새 키로 재제출하지 않는다. |

## 네이티브 API 계약

아래 경로는 backend 기준이다. 실제 요청에는 공용 Broker 주소의 승인된 게이트웨이 접두 경로를 정확히 한 번 결합한다.

1. `GET /api/v1/only/my-box/capabilities`로 지원과 준비 상태를 확인한다. `implemented`, `enabled`, `generation_enabled`가 true이고 실패 사유가 없어야 새 영상을 생성한다. 기능 OFF·미지원이면 레퍼런스 업로드·생성 제출 전에 종료하며 다른 프로젝트로 대체하지 않는다.
2. `GET /api/v1/only/my-box/workspace`는 조회만 한다. 명시적 My Box 실행에서 공간이 없고 `workspace_management_enabled=true`일 때만 같은 경로에 `POST {"explicit_selection":true}`로 최초 개인 공간을 만든다. UI 선택만으로 공간을 생성하지 않는다.
3. 선택 객체는 서버가 발급한 여섯 필드를 그대로 검증한다: `schema=hmb-only-my-box-selection-v1`, 정수 `version=1`, `selection_source=only_my_box`, `scope=personal_my_box`, `workspace_id=mbx_<소문자 16진수 32자리>`, 불리언 `explicit_selection=true`.
4. 영상 생성은 `POST /api/v1/generate/video`에 `hmb_generation_mode=only`, `hmb_generation_task`, `my_box_selection`, `my_box_title`, `client_request_id`와 실제 모델·영상 설정을 보낸다. `Idempotency-Key`는 같은 client request ID다. 일반 프로젝트·샷·사용자 권한 필드를 혼합하지 않는다.
5. 개인 Task는 `job-mybox-<소문자 16진수 32자리>`다. 응답 불명 시 같은 client request ID로 `POST /api/v1/jobs/{id}/refresh`를 수행한다. 자동 새 생성과 자동 새 키 발급은 금지한다.
6. 상세는 `GET /api/v1/only/my-box/items/{task_id}`, 원본은 같은 Task의 `/media?download=1`로 조회한다. 기존 Broker 인증을 사용하고 정확한 주소·길이·SHA256·영상 컨테이너를 검증한다.
7. Editing/Extension/Reference의 개인 원본은 본인 Task의 `/source-reference`에서 대상 client request ID·작업 종류에 묶인 단기 grant를 발급받는다. 다른 사용자나 제작 프로젝트의 Task로 우회하지 않는다.
8. Final은 capability의 `draft_final_detail_supported`, `draft_final_contract`와 원본 detail의 `draft_final`을 모두 확인한다. 원본 선택·workspace·source/child Task·현재 상태·7일 제한이 일치해야 한다. 권장 키 `mbx-final-v1-{source_task_hex32}`와 이미 저장된 실제 키를 보존한다.

기능 flag와 별도로 서버가 계정 한도·모델·작업 지원을 검증한다. `budget_limits_supported=false`인 서버는 지원하지 않는 비제로 한도 계정의 새 생성을 차단할 수 있다. 이 제한이나 제작 프로젝트 원본 재사용 미지원을 클라이언트가 우회하지 않는다. My Box의 별도 last-frame 이미지 출력은 현재 지원하지 않아 제출 전에 차단한다.

## 로컬 저장과 복구

기존 Generator의 `output_file`, 연결된 `FileOutputSettings`, `ProjectFileParameter` 및 Griptape 저장 템플릿을 사용한다. 새로운 공용 My Box 로컬 루트를 만들거나 사용자 폴더를 강제 변경하지 않는다. `My Box Title`은 웹 표시 제목이며 로컬 폴더 이름을 지정하지 않는다.

원본 MOV/MP4는 사용자가 정한 부모 폴더와 기본 이름을 유지하고 요청별 접미사를 붙여 저장한다. Draft·Final·반복 생성은 이전 파일을 덮어쓰지 않는다. 서버 지원 형식에 따른 확장자 선택은 기존 기능 검증을 따른다.

워크플로 체크포인트와 개인 복구 JSON에 Task·Broker·선택·확정 경로·SHA256을 보존한다. 저장본을 다시 열거나 동일 Task를 조회하면 기존 로컬 원본을 검증해 재사용한다. 이후 변경한 출력 설정으로 이전 결과를 이동하거나 새 렌더를 만들지 않는다. 원본 저장 성공은 선택적 UI 갱신 실패 때문에 생성 실패로 바뀌면 안 된다.

개인 결과에는 production 샷 provenance를 붙이지 않는다. Only 또는 일반 Video Loader 결과의 Color LUT 웹 업로드는 비활성화하며, 사용자 설정으로 개인 결과를 일반 제작 샷으로 재분류하지 않는다.

Broker 설정은 사용자 공용 설정을 기억한다. 기존 Task의 원점은 불변으로 보존하며, 서버 이전이나 기본 주소 변경만으로 오래된 Task의 원점을 자동 재기록하지 않는다. 이전 주소 폐쇄 시 기존 Task 조회·Final·업로드의 연결 연속성을 서버 담당이 검증해야 한다.

유지보수 중 접수되었거나 접수 결과가 불명인 작업의 임시 Cloud/TOS 레퍼런스는 시간 경과, 로컬 취소·삭제, 연결 오류 또는 큐 표시가 사라졌다는 이유로 정리하지 않는다. 원래 Broker·인증 사용자·요청 키·최종 Task에 묶어서 보존하고, 검증된 같은 Task의 최종 결과만 정리 근거로 사용한다. My Box의 `failed` 상태만으로는 최종 종료를 단정하지 않는다.

워크플로에는 불투명한 참조 보존 ID만 저장한다. 개인 로컬 관리 JSON은 이 프로세스가 만든 원격 경로·소유 범위와 미해결 상태만 기록하며, 인증정보·서명 URL·클라이언트 객체를 저장하지 않는다. 앱 재시작 시 이 JSON으로 삭제 클라이언트를 재구성하거나 과거 참조를 자동 삭제하지 않는다. 공급자 URL 및 원격 저장소의 기존 보관 기간을 연장하지 않는다.

## 검수 기준

| 구간 | 기대 결과 |
| --- | --- |
| 선택·바인딩 | Only의 명시 선택·저장·복원, Shot 전환 시 My Box 누출 없음, 일반 라이브러리 프로젝트에 미포함 |
| 웹 표시 | 제작리뷰 My Box 필터에서 본인 영상만 조회, 별도 사이트·웹 생성기 없음 |
| 서버 미지원·OFF | 업로드·생성 0회, 명확한 준비 상태 표시, 제작 프로젝트 fallback 없음 |
| 개인 권한 | 다른 사용자 Task·workspace·원본·grant·Confirm·Keep 교차 접근 거절 |
| 생성·편집·확장 | 지원 모델의 정확한 제출 옵션·개인 범위·입력 보존 |
| Draft·Final | 반복 480p 설정 유지, 동일 원본 Task 상태 동기화, 일회성 Final과 7일 제한 |
| 로컬·플레이어 | 원본 저장·즉시 재생·저장/재오픈·동일 Task 복구, 불필요한 서버 다운로드·새 생성 없음 |
| 취소·장애 | 중복 클릭·응답 유실·취소·노드 삭제·Broker 변경 후 잘못된 게시·재제출 없음 |
| 보관·공유 | 30일 관리 표시와 자동 정리 OFF 구분, Keep/Confirm 후에도 개인 권한 유지 |
| 기존 기능 | 두 제작 프로젝트·수동 Only 프로젝트·일반 리뷰·샷 LUT 게시에 회귀 없음 |

클라이언트 코드·합성 검사·실제 설치·인증된 서버 연동·실제 생성 결과는 별도 증거다. 무료 회귀 통과를 실제 유료 생성이나 운영 배포 완료로 표시하지 않는다.
