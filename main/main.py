import argparse

from utils.cctv_ui import QuietRequestHandler, create_app
from utils.pipeline import PrunedCCTVPipeline


def parse_args():
    parser = argparse.ArgumentParser(
        description="CCTV 영상 수신 -> Pruned YOLO 추론 -> 웹 UI 표시 파이프라인",
    )
    parser.set_defaults(use_roi=True)
    parser.add_argument("--host", default="0.0.0.0", help="Flask 서버 호스트")
    parser.add_argument("--port", type=int, default=5000, help="Flask 서버 포트")
    parser.add_argument("--cctv-index", type=int, default=None, help="기본 선택 CCTV 인덱스")
    parser.add_argument("--roi-path", default=None, help="ROI JSON 파일 경로")
    parser.add_argument("--use-roi", dest="use_roi", action="store_true", help="ROI 필터링 활성화")
    parser.add_argument("--no-roi", dest="use_roi", action="store_false", help="ROI 필터링 비활성화")
    parser.add_argument("--direct-url", default="", help="직접 사용할 CCTV URL")
    parser.add_argument("--direct-name", default="", help="직접 사용할 CCTV 이름")
    return parser.parse_args()


def main():
    args = parse_args()

    pipeline = PrunedCCTVPipeline(
        cctv_index=args.cctv_index,
        cctv_url=args.direct_url,
        cctv_name=args.direct_name,
        roi_path=args.roi_path,
        use_roi=args.use_roi,
    )
    app = create_app(pipeline)
    app.run(
        host=args.host,
        port=args.port,
        debug=False,
        threaded=True,
        request_handler=QuietRequestHandler,
    )


if __name__ == "__main__":
    main()
