# Security

보안 취약점이나 운영 경로를 공개 이슈에 게시하지 마십시오. 프로젝트
관리자에게 비공개 채널로 영향받는 버전, 재현 조건, 예상 영향과 최소
재현 자료를 전달하십시오. API 키, 정책 본문, 서명 키, 내부 미디어는
보고서에도 포함하지 않습니다.

## Repository visibility

이 저장소와 릴리스에는 승인된 HMB 운영자가 사용하는 내부 호스트 및
공유폴더 기본값이 포함됩니다. 저장소와 GitHub Release는 반드시
**Private**으로 유지하십시오. 공개 전환이 필요하면 내부 기본값을 모두
환경변수나 관리자 설정으로 치환하고 전체 릴리스 보안 검사를 다시
통과해야 합니다.


## Release verification

- 배포물은 `resources/build_release.py`로 생성한
  `HMB_GP_Production.zip`, `release-manifest.json`, `SHA256SUMS` 세 파일을
  함께 관리합니다.
