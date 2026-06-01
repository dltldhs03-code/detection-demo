"use client";

import { useEffect, useMemo, useRef, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL;
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || buildViewerWsUrl(API_URL);
const VIDEO_FEED_URL = buildVideoFeedUrl(API_URL);
const FRAME_IMAGE_URL = buildFrameImageUrl(API_URL);
const SHOW_OVERLAY = ["1", "true", "yes"].includes(
  String(process.env.NEXT_PUBLIC_SHOW_OVERLAY || "").toLowerCase(),
);
const STATUS_REFRESH_INTERVAL_MS = 1000;
const CHART_REFRESH_INTERVAL_MS = 1000;
const SYNC_DELAY_MS = Number(process.env.NEXT_PUBLIC_SYNC_DELAY_MS || 250);
const FRAME_REFRESH_INTERVAL_MS = Math.max(100, Number(process.env.NEXT_PUBLIC_FRAME_REFRESH_MS) || 250);

export default function HomePage() {
  const [status, setStatus] = useState(null);
  const [cctvs, setCctvs] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [wsState, setWsState] = useState("connecting");
  const [frameRefreshKey, setFrameRefreshKey] = useState(0);

  const frameImgRef = useRef(null);
  const overlayCanvasRef = useRef(null);
  const trafficUpChartRef = useRef(null);
  const trafficDownChartRef = useRef(null);
  const accidentProbabilityChartRef = useRef(null);
  const wsRef = useRef(null);
  const shouldReconnectRef = useRef(true);
  const reconnectTimerRef = useRef(null);
  const detectionQueueRef = useRef([]);
  const syncTimerRef = useRef(null);
  const lastAppliedFrameIdRef = useRef(-1);
  const lastChartDrawAtRef = useRef(0);
  const chartTimerRef = useRef(null);

  async function refreshStatus() {
    if (!API_URL) {
      setError("NEXT_PUBLIC_API_URL is not set.");
      setLoading(false);
      return;
    }

    try {
      const response = await fetch(`${API_URL}/api/status`, { cache: "no-store" });
      if (!response.ok) throw new Error(`Backend returned ${response.status}`);
      const data = await response.json();
      setStatus(data);
      setError("");
      setLoading(false);
    } catch (err) {
      setError(`Cannot reach backend: ${err.message}`);
      setLoading(false);
    }
  }

  async function refreshCctvs() {
    if (!API_URL) return;
    try {
      const response = await fetch(`${API_URL}/api/cctvs`, { cache: "no-store" });
      if (!response.ok) return;
      const data = await response.json();
      setCctvs(data.items || []);
    } catch (_err) {
      setCctvs([]);
    }
  }

  async function selectCctv(index) {
    if (!API_URL) return;
    const response = await fetch(`${API_URL}/api/select/${index}`, { method: "POST" });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      alert(data.error || "스트림 전환에 실패했습니다.");
      return;
    }
    setStatus(data.status);
    detectionQueueRef.current = [];
    lastAppliedFrameIdRef.current = -1;
    refreshCctvs();
  }

  useEffect(() => {
    refreshStatus();
    refreshCctvs();
    const intervalId = setInterval(refreshStatus, STATUS_REFRESH_INTERVAL_MS);
    return () => clearInterval(intervalId);
  }, []);

  useEffect(() => {
    if (!FRAME_IMAGE_URL) return undefined;
    const intervalId = setInterval(() => {
      setFrameRefreshKey(Date.now());
    }, FRAME_REFRESH_INTERVAL_MS);
    return () => clearInterval(intervalId);
  }, []);

  useEffect(() => {
    connectViewerWebSocket();
    startSyncLoop();
    return () => {
      shouldReconnectRef.current = false;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (syncTimerRef.current) clearInterval(syncTimerRef.current);
      if (chartTimerRef.current) clearTimeout(chartTimerRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  useEffect(() => {
    if (!status) return;
    scheduleChartRender(status);
    if (SHOW_OVERLAY) drawOverlay(status);
  }, [status]);

  useEffect(() => {
    const onResize = () => {
      if (SHOW_OVERLAY && status) drawOverlay(status);
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [status]);

  function connectViewerWebSocket() {
    if (!WS_URL) {
      setWsState("fallback");
      return;
    }
    try {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;
      setWsState("connecting");
      ws.onopen = () => setWsState("connected");
      ws.onmessage = (event) => {
        const message = JSON.parse(event.data);
        if (message.type === "ping") return;
        detectionQueueRef.current.push(message);
        detectionQueueRef.current.sort(
          (a, b) => Number(a.latest_detection?.frame_id || 0) - Number(b.latest_detection?.frame_id || 0),
        );
        setError("");
        setLoading(false);
      };
      ws.onclose = () => {
        setWsState("fallback");
        if (shouldReconnectRef.current) {
          reconnectTimerRef.current = setTimeout(connectViewerWebSocket, 1500);
        }
      };
      ws.onerror = () => ws.close();
    } catch (_err) {
      setWsState("fallback");
    }
  }

  function startSyncLoop() {
    syncTimerRef.current = setInterval(() => {
      const queue = detectionQueueRef.current;
      if (!queue.length) return;
      const targetTime = Date.now() - SYNC_DELAY_MS;
      let chosenIndex = -1;
      for (let index = 0; index < queue.length; index += 1) {
        const timestamp = Date.parse(queue[index]?.latest_detection?.timestamp || "");
        if (!Number.isFinite(timestamp)) continue;
        if (timestamp <= targetTime) chosenIndex = index;
        else break;
      }
      if (chosenIndex < 0) return;
      const nextStatus = queue.splice(0, chosenIndex + 1).pop();
      const frameId = Number(nextStatus?.latest_detection?.frame_id || 0);
      if (frameId <= lastAppliedFrameIdRef.current) return;
      lastAppliedFrameIdRef.current = frameId;
      setStatus(nextStatus);
    }, 40);
  }

  function scheduleChartRender(nextStatus) {
    const elapsed = Date.now() - lastChartDrawAtRef.current;
    if (elapsed >= CHART_REFRESH_INTERVAL_MS) {
      drawCharts(nextStatus);
      return;
    }
    if (chartTimerRef.current) return;
    chartTimerRef.current = setTimeout(() => {
      chartTimerRef.current = null;
      drawCharts(nextStatus);
    }, CHART_REFRESH_INTERVAL_MS - elapsed);
  }

  function drawCharts(nextStatus) {
    lastChartDrawAtRef.current = Date.now();
    renderCharts({
      trafficCount: nextStatus.traffic_count || 0,
      trafficUpHistory: nextStatus.traffic_up_history || [0],
      trafficDownHistory: nextStatus.traffic_down_history || [0],
      accidentProbabilityHistory: nextStatus.accident_probability_history || [0],
      trafficUpChart: trafficUpChartRef.current,
      trafficDownChart: trafficDownChartRef.current,
      accidentProbabilityChart: accidentProbabilityChartRef.current,
    });
  }

  function drawOverlay(nextStatus) {
    if (!SHOW_OVERLAY) return;
    const canvas = overlayCanvasRef.current;
    const image = frameImgRef.current;
    if (!canvas || !image) return;
    const ctx = fitOverlayCanvas(canvas, image);
    if (!ctx) return;

    const rect = image.getBoundingClientRect();
    ctx.clearRect(0, 0, rect.width, rect.height);

    const latest = nextStatus?.latest_detection || {};
    const detections = latest.detections || [];
    const rois = latest.rois || [];
    const sourceWidth = Math.max(1, Number(latest.frame_width) || 1);
    const sourceHeight = Math.max(1, Number(latest.frame_height) || 1);
    const scaleX = rect.width / sourceWidth;
    const scaleY = rect.height / sourceHeight;

    rois.forEach((roi) => {
      const points = roi.points || [];
      if (!points.length) return;
      const color = getDirectionColor(Number(roi.label));
      ctx.beginPath();
      points.forEach(([x, y], index) => {
        const sx = x * scaleX;
        const sy = y * scaleY;
        if (index === 0) ctx.moveTo(sx, sy);
        else ctx.lineTo(sx, sy);
      });
      ctx.closePath();
      ctx.fillStyle = `${color}24`;
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.fill();
      ctx.stroke();
    });

    detections.forEach((detection) => {
      const [x1, y1, x2, y2] = detection.bbox || [0, 0, 0, 0];
      const color = getDirectionColor(Number(detection.direction_label));
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.strokeRect(
        x1 * scaleX,
        y1 * scaleY,
        Math.max(0, (x2 - x1) * scaleX),
        Math.max(0, (y2 - y1) * scaleY),
      );
    });
  }

  const viewStatus = useMemo(() => status || buildEmptyStatus(loading, error), [status, loading, error]);
  const frameId = Number(viewStatus.latest_detection?.frame_id || 0);
  const frameSrc = FRAME_IMAGE_URL ? `${FRAME_IMAGE_URL}?frame_id=${frameId}&t=${frameRefreshKey}` : "";
  const streamStatusText = `${error || viewStatus.stream_status} · WS ${formatWsState(wsState)} · sync ${SYNC_DELAY_MS}ms · frame ${FRAME_REFRESH_INTERVAL_MS}ms`;

  return (
    <main className="page">
      <header className="topbar">
        <div>
          <p className="eyebrow">Selected CCTV</p>
          <h1>{viewStatus.selected_name}</h1>
        </div>
        <div className="status">
          <span className="status-label">Stream Status</span>
          <strong>{streamStatusText}</strong>
          <span className={`status-chip ${viewStatus.yolo_enabled ? "is-on" : "is-off"}`}>
            {viewStatus.yolo_enabled ? "YOLO ON" : "YOLO OFF"}
          </span>
          <p className="status-meta">{viewStatus.roi_path}</p>
        </div>
      </header>

      <section className="dashboard">
        <section className="left">
          <div className="section-head">
            <h2>Detection Screen</h2>
          </div>
          <div className="video-card">
            <div className="frame-stage">
              <img
                id="video-feed"
                ref={frameImgRef}
                src={frameSrc || undefined}
                alt="Live CCTV stream"
                onLoad={() => {
                  if (SHOW_OVERLAY) drawOverlay(viewStatus);
                }}
              />
              <canvas ref={overlayCanvasRef} aria-hidden="true" />
            </div>
          </div>

          <article className="metric-panel congestion-strip">
            <div className="section-head congestion-head">
              <h2>Traffic Status</h2>
            </div>
            <div className="congestion-grid">
              <div className="congestion-item downbound">
                <span className="congestion-label">하행 :</span>
                <strong className="congestion-value">{viewStatus.congestion_down ? "복잡" : "원활"}</strong>
              </div>
              <div className="congestion-item upbound">
                <span className="congestion-label">상행 :</span>
                <strong className="congestion-value">{viewStatus.congestion_up ? "복잡" : "원활"}</strong>
              </div>
            </div>
          </article>

          <section className="analytics">
            <article className="metric-panel traffic-panel">
              <div className="panel-head">
                <div>
                  <p className="metric-label">Traffic Analytics</p>
                  <h3>교통량 추이</h3>
                </div>
                <div className="traffic-total">
                  <span>현재 총 교통량</span>
                  <strong>{viewStatus.traffic_count}</strong>
                </div>
              </div>

              <div className="traffic-charts">
                <section className="traffic-chart-card downbound">
                  <div className="chart-title-row">
                    <div>
                      <p className="chart-kicker">Downbound</p>
                      <h4>하행 교통량</h4>
                    </div>
                    <strong className="chart-value">{viewStatus.traffic_down}</strong>
                  </div>
                  <canvas className="traffic-chart" width="640" height="240" ref={trafficDownChartRef} />
                </section>
                <section className="traffic-chart-card upbound">
                  <div className="chart-title-row">
                    <div>
                      <p className="chart-kicker">Upbound</p>
                      <h4>상행 교통량</h4>
                    </div>
                    <strong className="chart-value">{viewStatus.traffic_up}</strong>
                  </div>
                  <canvas className="traffic-chart" width="640" height="240" ref={trafficUpChartRef} />
                </section>
              </div>
            </article>

            <article className="metric-panel accident-panel">
              <div className="panel-head">
                <div>
                  <p className="metric-label">Accident Risk</p>
                  <h3>사고 발생 확률</h3>
                </div>
                <div className="probability-badge">{viewStatus.accident_status}</div>
              </div>
              <div className="accident-body">
                <div className="probability-block">
                  <p className="metric-note">교통량 기반 추정치</p>
                  <div className="probability-value">
                    <strong>{viewStatus.accident_probability}</strong>
                    <span>%</span>
                  </div>
                  <div className="probability-meter">
                    <div className="probability-fill" style={{ width: `${viewStatus.accident_probability}%` }} />
                  </div>
                </div>
                <div className="accident-chart-wrap">
                  <canvas className="traffic-chart" width="640" height="240" ref={accidentProbabilityChartRef} />
                </div>
              </div>
            </article>
          </section>
        </section>

        <aside className="right">
          <div className="section-head">
            <h2>CCTV List</h2>
          </div>
          <div className="list-card">
            <div className="cctv-list">
              {cctvs.map((cctv) => (
                <button
                  key={`${cctv.index}-${cctv.name}`}
                  className={`cctv-item ${cctv.selected ? "is-active" : ""}`}
                  onClick={() => selectCctv(cctv.index)}
                  type="button"
                >
                  <span className="cctv-index">{String(cctv.index + 1).padStart(3, "0")}</span>
                  <span className="cctv-name">{cctv.name}</span>
                </button>
              ))}
            </div>
          </div>
        </aside>
      </section>
    </main>
  );
}

function buildViewerWsUrl(apiUrl) {
  if (!apiUrl) return "";
  return `${apiUrl.replace(/^http/, "ws").replace(/\/$/, "")}/ws/viewer`;
}

function buildVideoFeedUrl(apiUrl) {
  if (!apiUrl) return "";
  return `${apiUrl.replace(/\/$/, "")}/video_feed`;
}

function buildFrameImageUrl(apiUrl) {
  if (!apiUrl) return "";
  return `${apiUrl.replace(/\/$/, "")}/frame.jpg`;
}

function formatWsState(state) {
  if (state === "connected") return "연결됨";
  if (state === "connecting") return "연결 중";
  return "fallback";
}

function fitOverlayCanvas(canvas, image) {
  const rect = image.getBoundingClientRect();
  if (!rect.width || !rect.height) return null;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.floor(rect.width * ratio));
  canvas.height = Math.max(1, Math.floor(rect.height * ratio));
  canvas.style.width = `${rect.width}px`;
  canvas.style.height = `${rect.height}px`;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  return ctx;
}

function getDirectionColor(directionLabel) {
  if (directionLabel === 0) return "#32e67f";
  if (directionLabel === 1) return "#ffab4d";
  return "#ff6b6b";
}

function buildEmptyStatus(loading, error) {
  return {
    selected_name: "-",
    stream_status: error ? "연결 오류" : loading ? "준비 중" : "대기 중",
    traffic_count: 0,
    traffic_up: 0,
    traffic_down: 0,
    traffic_up_history: [0],
    traffic_down_history: [0],
    accident_probability: 0,
    accident_probability_history: [0],
    accident_status: "-",
    congestion_up: false,
    congestion_down: false,
    yolo_enabled: false,
    roi_path: API_URL || "NEXT_PUBLIC_API_URL is not set",
    player_url: VIDEO_FEED_URL,
    message_sequence: 0,
    latest_detection: null,
  };
}

function fitCanvas(canvas) {
  if (!canvas) return null;
  const ratio = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.max(1, Math.floor(rect.width * ratio));
  canvas.height = Math.max(1, Math.floor(rect.height * ratio));
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  return ctx;
}

function drawLineChart(canvas, values, options) {
  const ctx = fitCanvas(canvas);
  if (!ctx) return;
  const width = canvas.getBoundingClientRect().width;
  const height = canvas.getBoundingClientRect().height;
  const padding = { top: 18, right: 12, bottom: 24, left: 12 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const maxValue = Math.max(6, ...values, options.maxFloor || 0);
  const points = values.length > 1 ? values : [0, values[0] || 0];

  ctx.clearRect(0, 0, width, height);
  ctx.strokeStyle = options.gridColor;
  ctx.lineWidth = 1;
  for (let i = 0; i < 4; i += 1) {
    const y = padding.top + (innerHeight / 3) * i;
    ctx.beginPath();
    ctx.moveTo(padding.left, y);
    ctx.lineTo(width - padding.right, y);
    ctx.stroke();
  }

  const gradient = ctx.createLinearGradient(0, padding.top, 0, height - padding.bottom);
  gradient.addColorStop(0, options.fillTop);
  gradient.addColorStop(1, options.fillBottom);

  ctx.beginPath();
  points.forEach((value, index) => {
    const x = padding.left + (innerWidth * index) / Math.max(1, points.length - 1);
    const y = padding.top + innerHeight - (Math.min(value, maxValue) / maxValue) * innerHeight;
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.lineTo(width - padding.right, height - padding.bottom);
  ctx.lineTo(padding.left, height - padding.bottom);
  ctx.closePath();
  ctx.fillStyle = gradient;
  ctx.fill();

  ctx.beginPath();
  points.forEach((value, index) => {
    const x = padding.left + (innerWidth * index) / Math.max(1, points.length - 1);
    const y = padding.top + innerHeight - (Math.min(value, maxValue) / maxValue) * innerHeight;
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = options.lineColor;
  ctx.lineWidth = 3;
  ctx.stroke();
}

function renderCharts({
  trafficCount,
  trafficUpHistory,
  trafficDownHistory,
  accidentProbabilityHistory,
  trafficUpChart,
  trafficDownChart,
  accidentProbabilityChart,
}) {
  drawLineChart(trafficUpChart, trafficUpHistory, {
    lineColor: "#3cf28a",
    fillTop: "rgba(60, 242, 138, 0.32)",
    fillBottom: "rgba(60, 242, 138, 0.02)",
    gridColor: "rgba(160, 184, 220, 0.14)",
    maxFloor: trafficCount + 2,
  });
  drawLineChart(trafficDownChart, trafficDownHistory, {
    lineColor: "#ffae42",
    fillTop: "rgba(255, 174, 66, 0.32)",
    fillBottom: "rgba(255, 174, 66, 0.02)",
    gridColor: "rgba(160, 184, 220, 0.14)",
    maxFloor: trafficCount + 2,
  });
  drawLineChart(accidentProbabilityChart, accidentProbabilityHistory, {
    lineColor: "#ff8a7a",
    fillTop: "rgba(255, 138, 122, 0.28)",
    fillBottom: "rgba(255, 138, 122, 0.02)",
    gridColor: "rgba(160, 184, 220, 0.14)",
    maxFloor: 100,
  });
}
