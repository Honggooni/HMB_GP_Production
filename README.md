# HMB GP Production

> **Private repository only.** This source tree and its production release keep
> authorized internal host/share defaults required by the HMB team workflow.
> Do not make the GitHub repository or release assets public without replacing
> those defaults and repeating the release security audit.

## HMB Seedance 2.0 for Volcengine Ark

`HMBSeedance20VideoGeneration` keeps the existing file, class, and display name,
but its execution path now calls the official
Volcengine Ark asynchronous API directly. It submits
`POST /api/v3/contents/generations/tasks`, polls
`GET /api/v3/contents/generations/tasks/{id}`, then immediately downloads
`content.video_url` to the configured project MP4. The `video_url` property
owns the single result preview, while `VIDEO_OUT` is the sole graph output and
publishes the same local artifact.

Configure the user-owned Volcengine credential in Griptape
`Settings > Secrets > ARK_API_KEY`. The key is read only when the node runs and
is never stored in a node parameter, output, log, manifest, or release archive.
The Ark account must separately have Seedance model access, sufficient balance
or package entitlement, and permission for the selected model.

This HMB generator also maintains an invisible per-login usage ledger at
`\\fin-rcomp1\Composite_Team\00.CompSource\Griptape_list\{user_id}\{user_id}.json`.
The logged-in Griptape `user_id` is used as the folder and file identity. Months
are appended inside the same JSON document, and a task ID is updated rather than
counted twice by polling, Resume, or Refresh. Only
`HMBSeedance20VideoGeneration` emits these records; other video generators are
outside this ledger. The node UI and outputs do not expose usage accounting.

Usage events contain only task identity, status, model/options, returned token
counts, the price snapshot used for an estimate, and timestamps. They never
contain a prompt, API key, authorization value, result/reference URL, or media
payload. Each event is first persisted under the current Windows user's local
application-data queue and then synchronized in the background. If the network
share is unavailable, rendering is not changed and the queued event is retried
by a later execution. Shared JSON updates use a per-user lock and a
same-directory atomic replacement; an unreadable existing ledger is retained
rather than overwritten.

Volcengine Ark requires reference videos to be provider-reachable URLs. When a
local MP4 is connected, the existing HMB node can publish it temporarily through
the selected upload service, use the resulting signed `https://` URL for that
execution, and delete the temporary object on success, ordinary failure, timeout,
or local cancellation. If the create POST outcome is unknown, the object is
retained for up to 30 minutes so a task accepted by Ark can still fetch it.
Keep `Auto Publish Local Videos` enabled. The existing upload service remains
the default for saved workflows. To use a private Volcengine TOS bucket instead,
select `Local Video Upload = Volcengine TOS` and configure these Griptape Secrets:

- `TOS_ACCESS_KEY_ID`: least-privilege TOS IAM access key ID
- `TOS_SECRET_ACCESS_KEY`: matching secret access key
- `TOS_BUCKET_NAME`: private bucket in the selected region

The defaults use region `cn-beijing`, endpoint
`tos-cn-beijing.volces.com`, and a 24-hour signed HTTPS URL. TOS object keys use
random identifiers rather than local filenames. Temporary objects are deleted
best-effort after an unambiguous execution; configure a short bucket lifecycle
as a crash-recovery backstop. An already-public `https://` URL or Volcengine
`asset://` reference bypasses upload entirely. The local port value and workflow
remain unchanged. `ARK_API_KEY` is sent only to the Ark API, while TOS credentials
are used only by the official TOS SDK and are never included in the signed URL.

Reference images use one ordered `list[str]` input on the existing HMB Seedance
2.0 node. Connect the complete Image Asset Library selection with one wire:

`HMBImageAssetLibrary.Video Generation Out -> HMB Seedance 2.0 Video Generation.Reference Images`

Reference videos also use one ordered `list[str]` input. Connect the complete
Video Picker selection with one wire:

`HMBVideoPickerLibrary.VIDEO_OUT -> HMB Seedance 2.0 Video Generation.Reference Videos`

The Picker's visible `@video1`, `@video2`, and `@video3` order becomes the Ark
payload order without reconnecting individual videos. Seedance accepts at most
three reference videos; a Picker selection of four or more fails before any
upload or billable task POST and is never truncated. The former
`reference_video_1`, `reference_video_2`, and `reference_video_3` parameters stay
registered but hidden so saved scalar-port workflows can still execute when the
new list input is empty. A populated `Reference Videos` list always takes
precedence over those compatibility values.

Before publishing a selected local reference, Video Picker resolves its
`project_video_path` against the active Griptape project and verifies that the
file is non-empty and readable. If that project copy is stale but the source
`video_path` is still readable, the source path is used and the stale project
metadata is removed from `PICKER_OUT`. If any selected local-origin video has no
readable project or source copy, the complete ordered selection is blocked:
`VIDEO_OUT` becomes empty, `PICKER_OUT.media_blocked` is `true`, and the node
instructs the operator to re-import the MP4 or regenerate the Playblast. It
never forwards only the remaining videos or silently runs Seedance without the
missing reference.

Ark does not accept Base64/local video references, so the node resolves
project-relative MP4 paths and performs the temporary publication step before
the billable task POST.

Disable `Auto Publish Local Videos` only when every video input is already a
provider-reachable `https://` URL or Volcengine `asset://` reference.

The result UI displays one video preview. `video_url` is preview/property-only,
and `VIDEO_OUT` is the single output connector to the same artifact. Existing
workflows wired from the former upper `Video` connector must reconnect once to
`VIDEO OUT`; generation, download, and billing behavior are unchanged.
`generation_id` and `generation_status`
now live in the collapsed Status group together with the Standard-style
`Refresh / Retrieve Result` button. Refresh performs GET requests only: it can
retrieve a known task, or list recent candidates after an ambiguous create
response, but it never chooses a candidate or creates another billed task.

`Reference Images` accepts at most nine ordered items and can encode supported
local images as data URIs. Ten or more items fail before task creation rather
than being truncated. `reference_audio` accepts at most three public, `asset://`,
data-URI, or local MP3/WAV references; audio requires at least one image or
video reference. A newly added node starts with `Generate Audio = False`; the
user can turn it on normally, and a value already saved in a workflow is kept.
Request size, media size, duration, ratio, and model-specific
resolution constraints are validated before submission. The Volcengine CN
contract offers 480p, 720p, 1080p, and 4k on Seedance Standard; Fast and Mini
remain restricted to 480p and 720p. Seedance Standard, Fast, and Mini map to
the official `doubao-seedance-*` model IDs. Stopping the
node stops local polling only; a task already accepted by Volcengine may continue
remotely and may still incur charges. Copy the retained `generation_id` into
`Resume Task ID` before rerunning after a timeout, cancellation, download error,
or save error; Resume skips the create-task POST and continues polling/download.
Create POSTs are attempted exactly once with a 300-second response timeout. A
network or response failure is labeled `submission_unknown` with only a safe
error type and phase. Use Refresh to inspect recent Ark candidates before any
new execution; the node never retries an ambiguous POST automatically.
Result downloads are streamed with a size cap, and every redirect destination is
checked to prevent credentials or requests from reaching a private network.

For synchronized selection, connect both branches from the same Asset Library:

- `IMAGE_ASSET_OUT -> HMBPromptLibrary.IMAGE_ASSET_IN` keeps Prompt image rows
  in the exact selected order. Adding, removing, or reordering a selected asset
  activates, deactivates, or moves only its Asset-managed Prompt row. While the
  edge is connected, selected upstream rows exclusively own active `@imageN`
  slots; the Prompt image `+` button is locked because new rows must be added in
  Image Asset Library. Native/manual rows sleep outside that namespace, the `+`
  button unlocks, and those rows return when the edge is removed.
- `Video Generation Out -> Reference Images` sends the same ordered
  media list to Seedance in one connection.

Both branches are produced from one media-resolution snapshot. If a selected
image cannot be resolved, that row is omitted from both branches, the remaining
rows receive the same packed numbering, and `media_resolution` plus `warnings`
identify the unresolved `source_uid`; Prompt never silently binds that token to
a different image.

If a removed row was referenced by editable Prompt text, its token becomes a
non-binding deselection marker instead of silently pointing at a different
image. Manually created Prompt rows remain independent.
Their complete authored settings are retained in a dormant manual cache, while
deselected managed rows retain Target, Role, Color Pick, and Range settings in
a separate `source_uid` cache for an exact later reselect.

## Architecture contract

- 네 라이브러리는 각각 단독으로 사용할 수 있으며 15개 조합이 모두 유효합니다.
- `HMBPromptLibrary`는 네 가지 동등한 모드를 제공합니다: Prompt 단독, Prompt+Asset, Prompt+Picker, Prompt+Asset+Picker.
- Prompt의 두 입력은 읽을 수 있는 어떤 연결값도 수용하며, 알 수 없는 필드·중복·최대 구조화 개수 초과 데이터도 일반 사용자 의도로 보존합니다.
- HMB 자동화의 단일 부모 경계는 `HMBPromptLibrary.PROMPT_OUT -> HMBAgentLibrary.prompt` 직접 연결입니다. Agent는 Asset, Picker, 릴레이, 복사된 문구 또는 이름이 같은 다른 노드를 HMB Prompt로 대신 인정하지 않습니다.
- 위 직접 연결이 없으면 `HMBAgentLibrary`는 설치된 Griptape Standard Library Agent 그대로 실행됩니다.

HMBImageAssetLibrary, HMBVideoPickerLibrary, HMBPromptLibrary, HMBAgentLibrary는 각각 독립적으로 사용할 수 있습니다. 1·2·3·4개 조합 15가지는 모두 유효하며, 연결은 데이터 동기화와 자동화를 추가할 뿐 편집이나 실행의 선행조건이 아닙니다.

## Video Picker generation choices

`Original`, `Mask`, `Depth`, `Motion Guide` are selection-only checkboxes.
Changing a checkbox does not run Maya, FFmpeg, or a cache lookup. Press
`Generate Playblast` to append the checked subset to the current-cut video
catalog. A checked Original is part of that frozen request and a failed
Original cannot silently publish only Mask, Depth, and Motion Guide. Generated
and loaded MP4 assets are never overwritten by slot number. Card thumbnails are
static and never play inline: the centered button routes that asset to the main
Preview and toggles play/pause there. The entire lower information area selects
or deselects the card. Selected cards use a thicker, brighter neon outline and
keep delete at the upper-right. Dragging selected cards changes the transient
`@video1..@videoN` order. Metadata-only deletion safely pauses a deleted active
preview, selects the next valid preview when available, and never leaves the
Picker stuck in a busy state. Up to ten selected assets are published through
`PICKER_OUT` as synchronized Prompt metadata and through `VIDEO_OUT` as the same
ordered `list[str]` media paths. There are no public per-video output ports.

Snapshot and Video share the main viewport. A completed Snapshot switches the
viewport label to `(Snapshot)` immediately; the left/right controls traverse a
stable history of up to ten stills. The center transport switches to `(Video)`
and toggles only the main video between `▶` and `Ⅱ`. The former local `Open`
control is removed because the current-cut `Load` action is the sole MP4 import
path.

For Maya 2024–2027, Depth uses fresh unlit `surfaceShader` buckets and the raw
`ogsRender` renderer target. Every source frame is checked at full resolution;
at most two levels of RGB quantization drift are normalized to exact gray8,
while stronger chroma is rejected. Color, Depth, and Motion Guide project copies
use the Griptape 0.93 `bytes` write contract.

## Runtime

- Windows 10/11
- Python 3.12
- Griptape Nodes Engine 0.93.x
- Griptape Standard Library 0.81.x 이상
- Autodesk Maya 2024–2027 (`HMBVideoPickerLibrary`의 Maya 기능 사용 시)
- `Pillow==12.3.0`, `imageio-ffmpeg==0.6.0`

## Install

1. `HMB_GP_Production.zip`의 단일 `HMB_GP_Production` 폴더를 GriptapeNodes `libraries` 폴더에 배치합니다.
2. `SHA256SUMS`로 ZIP과 `release-manifest.json`을 확인합니다.
3. 관리자가 만든 전용 정책 공유를 일반 Reader 계정으로 검증한 뒤, 검증 스크립트가 사용자 환경변수 `HMB_AGENT_POLICY_PATH`를 설정하게 합니다. 정책 파일과 그 파일의 정확한 경로는 저장소·ZIP에 포함되지 않습니다.
4. Griptape Nodes를 다시 시작하고 라이브러리 버전을 확인합니다.

기존 설치를 갱신할 때는 임시 폴더에서 ZIP을 검증한 뒤 전체 폴더를 교체하십시오. 서로 다른 버전 파일을 overlay 방식으로 섞지 마십시오.

정책 공유폴더는 사용량 원장이 쓰이는 `Griptape_list` 트리와 분리해야 합니다. 서버 관리자는 기존 공유 트리 밖의 새 로컬 경로에서 `resources/admin/Configure_HMB_Agent_Policy_Share.ps1`을 실행해 별도 SMB 공유를 만듭니다. 이 스크립트는 경로가 다른 일반 공유에 노출되지 않았는지 확인하고, reparse point와 부모 `Delete child` 우회를 거부하며, SMB 암호화·오프라인 캐시 금지·관리자 Full/Reader Read·보호된 NTFS ACL을 적용한 뒤 실제 ACE를 재검증합니다.

일반 Reader 계정은 `resources/admin/Test_HMB_Agent_Policy_Share.ps1`에 관리자가 출력한 UNC와 SHA-256, 설치된 라이브러리 root, PolicyAdmins 그룹을 전달합니다. 테스트는 정책 읽기·해시·서명을 확인하고 생성·이름변경·삭제가 정확히 `Access denied`인지 확인합니다. 모든 검사가 성공한 경우에만 사용자 환경변수를 설정합니다. Griptape 재시작 후 Agent 정책 회귀검사를 통과하면 서버 관리자가 `resources/admin/Finalize_HMB_Agent_Policy_Migration.ps1`로 기존 광범위 공유의 임시 정책 사본을 제거합니다.

전체 명령 순서는 `resources/admin/HMB_Agent_Policy_Share_Runbook.md`를 따릅니다.

## Project root

새 HMBImageAssetLibrary의 기본 catalog는 `\\fin-rcomp1\Composite_Team\projects_AI`입니다. 기존 저장값과 사용자가 선택한 경로가 항상 우선하며, 관리자는 `HMB_IMAGE_PROJECTS_ROOT` 환경변수로 기본값을 변경할 수 있습니다.

## Image asset registration storage

- `IMAGE_IMPORT_IN` 이미지를 Add로 등록하면 프로젝트 루트가 아닌 기존 하위 Asset Folder를 선택해야 하며, 새 폴더를 만들지 않고 `선택한 Asset Folder/원본 파일명`으로 직접 복사합니다. 예: `CH/hero.png`.
- `LoadImage`가 전달하는 `{inputs}/...`, `{outputs}/...` 프로젝트 매크로는 서버의 현재 프로젝트 경로로 해석한 뒤 복사합니다.
- `.json/hmb_image_assets.json`은 등록 이미지의 상대경로, Asset ID, Image Name, Main Type, Sub Type을 보관하는 프로젝트 공용 manifest입니다. HMBImageAssetLibrary는 이 파일을 등록 여부와 메타데이터의 최종 기준으로 사용합니다.
- `.json/.hmb_image_assets.lock`은 여러 사용자나 프로세스가 같은 manifest를 동시에 수정하지 못하도록 운영체제/SMB 잠금을 거는 영구 coordination 파일입니다. 이미지나 오류 로그가 아니며, 클라이언트가 프로젝트를 사용하는 동안 삭제하거나 편집하지 마십시오.
- 이전 버전이 프로젝트 루트에 만든 두 파일은 다음 manifest 저장 시 `.json` 관리 폴더 구조로 자동 이전됩니다. `.json`은 이미지 스캔과 HMB 폴더 트리에서 제외됩니다.
- 검증된 프로젝트 어셋을 HMBPromptLibrary의 `ASSET_IN`에 연결하면 등록 Main Type과 Sub Type이 실제 Prompt 바인딩으로 동기화됩니다. Target은 Main Type에 맞는 기본값으로 시작하지만 사용자가 자유롭게 변경할 수 있습니다.

## Security and operation

- 외부 Maya scene은 신뢰된 production source만 사용하십시오.
- Agent 정책은 배포물에 포함되지 않으며 `HMB_AGENT_POLICY_PATH`에서 매 실행 시 읽고 공개키 서명·버전·계약 해시를 검증합니다. 정확한 HMBPromptLibrary 직접 연결이 없으면 순정 Agent로 동작하지만, 그 연결이 존재하는 경우 경로 미설정, 공유 폴더 장애 또는 payload 검증 실패 시 순정 Agent나 모델을 호출하지 않고 명시적인 `HMB POLICY REQUIRED` 오류로 중단합니다.
- Ark, Griptape Cloud 및 TOS API key는 Griptape Settings > Secrets에만 저장하며 소스·워크플로·로그·배포 ZIP에 포함하지 않습니다.
- 외부 FFmpeg는 명시적으로 지정한 경우에만 사용하고, 기본은 pinned bundled FFmpeg입니다.
- 프레임·해상도·디스크·import 예산은 사용자 아이디어를 제한하는 정책이 아니라 호스트 중단과 데이터 손상을 방지하는 기술 경계입니다.

자세한 내용은 `SECURITY.md`, 변경 이력은 `CHANGELOG.md`, 구성요소는 `SBOM.spdx.json`을 참고하십시오.
