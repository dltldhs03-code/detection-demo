# Utils Modules

`main.py`를 제외한 보조 파이썬 모듈들은 모두 `utils/` 아래에 정리되어 있습니다.

## 파일 역할

### `app_config.py`
- 프로젝트 전역 설정을 모아둔 파일입니다.
- 모델 경로, 환경변수, 임계값, CCTV 기본 인덱스 같은 상수를 관리합니다.
- `pruned.pt`, `pruned.yaml` 같은 로컬 파일 경로를 해석합니다.

### `pruned_yolo_cctv.py`
- Pruned YOLO detector 전용 래퍼입니다.
- `PrunedYOLODetector` 클래스를 통해 모델을 로드하고 `predict()`를 제공합니다.
- 전체 시스템 조합은 하지 않고 detection만 담당합니다.

### `detector.py`
- 실제 YOLO 모델 로드와 inference 세부 로직을 담당합니다.
- `load_model()`과 `run_inference()`가 들어 있습니다.
- detector 래퍼나 pipeline에서 공통으로 사용합니다.

### `stream.py`
- CCTV 목록 조회와 영상 스트림 연결을 담당합니다.
- ITS Open API 호출, 스트림 URL 해석, `VideoCapture` 연결, 프레임 읽기 로직이 들어 있습니다.

### `roi.py`
- ROI 데이터 로드, 경로 생성, 점-다각형 포함 여부 검사 기능을 담당합니다.
- ROI를 직접 그려 저장하는 `ROISelector` 도구도 포함합니다.

### `analysis.py`
- detection 결과를 분석하는 로직이 들어 있습니다.
- ROI 필터링, 상행/하행 분리, 교차 면적 계산, 중심 이동 평균 계산, 복잡 여부 판단을 담당합니다.

### `renderer.py`
- 프레임 시각화 전용 모듈입니다.
- ROI 오버레이와 bbox 그리기 같은 표시 로직을 담당합니다.

### `remote.py`
- 외부 백엔드 전송 기능을 담당합니다.
- HTTP payload 생성, WebSocket 전송, 재연결 처리, fallback 전송이 들어 있습니다.

### `pipeline.py`
- 전체 시스템 조합을 담당하는 핵심 파이프라인입니다.
- stream, detector, analysis, renderer, remote를 연결해서 한 프레임 처리 흐름을 만듭니다.
- `PrunedCCTVPipeline` 클래스가 여기 있습니다.

### `cctv_ui.py`
- Flask 기반 웹 UI 서비스 모듈입니다.
- 파이프라인 결과를 MJPEG 영상과 상태 API로 제공하고, 템플릿과 연결합니다.
