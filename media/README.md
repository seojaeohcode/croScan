# 발표·영상 제작 소스

## video/ — Remotion 영상

- `src/`: React·Remotion 장면 구성.
- `public/`: 장면에 사용하는 이미지·폰트 등 로컬 자산.
- `STORYBOARD.md`: 장면 설계.
- 설치·미리보기: `cd media/video`, `npm ci`, `npm run studio`.
- 렌더: `npm run render`. Remotion 및 각 자산의 사용 조건을 확인합니다.

## slides/ — HTML 기반 발표 자료

- `parts/`: 슬라이드별 원본 HTML. `img/`, `svg/`: 발표 자산.
- `python build.py`: 조각을 합쳐 `deck.html` 생성.
- `render.mjs`, `export_slides.mjs`, `make_pptx.py`: 제작 당시의 렌더·내보내기 도구. 로컬 런타임 경로와 출력 경로를 환경에 맞춰 설정해야 합니다.
- 이 폴더는 제작 소스 보관본입니다. 배포용 최종 PDF·PPTX는 [`docs/presentation/`](../docs/presentation/)을 사용합니다.

## capture/ — 실제 앱 시연 녹화·편집

- 작업반장(`A/`)·안전관리자(`S/`) 화면 조작, 장면 명세, 자막, 클립 결합 스크립트.
- 최종 콘티·자막 기록을 함께 보관합니다. 실행 결과 로그와 화면에 입력한 개인 세션은 포함하지 않습니다.
- 제작 당시의 로컬 경로·PRAI·FFmpeg 등 외부 도구에 의존하는 보관본입니다. 그대로 실행하는 앱 설치 경로가 아니며, 재사용 시 경로·의존성을 맞춰야 합니다.

`node_modules`, 중간 렌더 파일, 중복 구버전 발표 파일, 개인 세션·작업 로그는 포함하지 않았습니다. 앱 QA 시스템은 [`server/qa.py`](../server/qa.py)에 있습니다.
