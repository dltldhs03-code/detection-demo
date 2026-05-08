"use client";

import { useEffect, useRef, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL;
const STATUS_REFRESH_INTERVAL_MS = 1000;

export default function HomePage() {
  const [status, setStatus] = useState(null);
  const [cctvs, setCctvs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const trafficUpChartRef = useRef(null);
  const trafficDownChartRef = useRef(null);
  const accidentProbabilityChartRef = useRef(null);

  async function refreshStatus() {
    if (!API_URL) {
      setError("NEXT_PUBLIC_API_URL is not set.");
      setLoading(false);
      return;
    }

    try {
      const response = await fetch(`${API_URL}/api/status`, { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`Backend returned ${response.status}`);
      }
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

    try {
      const response = await fetch(`${API_URL}/api/select/${index}`, {
        method: "POST",
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        alert(data.error || "스트림 전환에 실패했습니다.");
        return;
      }
      setStatus(data.status);
      await refreshCctvs();
    } catch (err) {
      alert(`스트림 전환에 실패했습니다: ${err.message}`);
    }
  }

  useEffect(() => {
    refreshStatus();
    refreshCctvs();
    const intervalId = setInterval(refreshStatus, STATUS_REFRESH_INTERVAL_MS);
    return () => clearInterval(intervalId);
  }, []);

  useEffect(() => {
    if (!status) return;
    renderCharts({
      trafficCount: status.traffic_count || 0,
      trafficUpHistory: status.traffic_up_history || [0],
      trafficDownHistory: status.traffic_down_history || [0],
      accidentProbabilityHistory: status.accident_probability_history || [0],
      trafficUpChart: trafficUpChartRef.current,
      trafficDownChart: trafficDownChartRef.current,
      accidentProbabilityChart: accidentProbabilityChartRef.current,
    });
  }, [status]);

  useEffect(() => {
    function handleResize() {
      if (!status) return;
      renderCharts({
        trafficCount: status.traffic_count || 0,
        trafficUpHistory: status.traffic_up_history || [0],
        trafficDownHistory: status.traffic_down_history || [0],
        accidentProbabilityHistory: status.accident_probability_history || [0],
        trafficUpChart: trafficUpChartRef.current,
        trafficDownChart: trafficDownChartRef.current,
        accidentProbabilityChart: accidentProbabilityChartRef.current,
      });
    }

    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [status]);

  const viewStatus = status || buildEmptyStatus(loading, error);
  const videoUrl = normalizeBackendUrl(
    viewStatus.player_url || viewStatus.stream_url || viewStatus.cctv_url || "",
  );

  return (
    <main className="page">
      <header className="topbar">
        <div>
          <p className="eyebrow">Selected CCTV</p>
          <h1 id="selected-name">{viewStatus.selected_name}</h1>
        </div>
        <div className="status">
          <span className="status-label">Stream Status</span>
          <strong id="stream-status">{error || viewStatus.stream_status}</strong>
          <span
            className={`status-chip ${viewStatus.yolo_enabled ? "is-on" : "is-off"}`}
            id="yolo-chip"
          >
            {viewStatus.yolo_enabled ? "YOLO ON" : "YOLO OFF"}
          </span>
          <p className="status-meta" id="roi-path">
            {viewStatus.roi_path}
          </p>
        </div>
      </header>

      <section className="dashboard">
        <section className="left">
          <div className="section-head">
            <h2>Detection Screen</h2>
          </div>
          <div className="video-card">
            <CctvVideoPlayer src={videoUrl} fallbackSrc={API_URL ? `${API_URL}/video_feed` : ""} />
          </div>

          <section className="analytics">
            <article className="metric-panel traffic-panel">
              <div className="panel-head">
                <div>
                  <p className="metric-label">Traffic Analytics</p>
                  <h3>교통량 추이</h3>
                </div>
                <div className="traffic-total">
                  <span>현재 총 교통량</span>
                  <strong id="traffic-count">{viewStatus.traffic_count}</strong>
                </div>
              </div>

              <div className="traffic-charts">
                <section className="traffic-chart-card downbound">
                  <div className="chart-title-row">
                    <div>
                      <p className="chart-kicker">Downbound</p>
                      <h4>하행 교통량</h4>
                    </div>
                    <strong className="chart-value" id="traffic-down">
                      {viewStatus.traffic_down}
                    </strong>
                  </div>
                  <canvas
                    id="traffic-down-chart"
                    className="traffic-chart"
                    width="640"
                    height="240"
                    ref={trafficDownChartRef}
                  />
                </section>

                <section className="traffic-chart-card upbound">
                  <div className="chart-title-row">
                    <div>
                      <p className="chart-kicker">Upbound</p>
                      <h4>상행 교통량</h4>
                    </div>
                    <strong className="chart-value" id="traffic-up">
                      {viewStatus.traffic_up}
                    </strong>
                  </div>
                  <canvas
                    id="traffic-up-chart"
                    className="traffic-chart"
                    width="640"
                    height="240"
                    ref={trafficUpChartRef}
                  />
                </section>
              </div>
            </article>

            <article className="metric-panel accident-panel">
              <div className="panel-head">
                <div>
                  <p className="metric-label">Accident Risk</p>
                  <h3>사고 발생 확률</h3>
                </div>
                <div className="probability-badge" id="accident-status">
                  {viewStatus.accident_status}
                </div>
              </div>

              <div className="accident-body">
                <div className="probability-block">
                  <p className="metric-note">교통량 기반 추정치</p>
                  <div className="probability-value">
                    <strong id="accident-probability">
                      {viewStatus.accident_probability}
                    </strong>
                    <span>%</span>
                  </div>
                  <div className="probability-meter">
                    <div
                      className="probability-fill"
                      id="accident-probability-fill"
                      style={{ width: `${viewStatus.accident_probability}%` }}
                    />
                  </div>
                </div>

                <div className="accident-chart-wrap">
                  <canvas
                    id="accident-probability-chart"
                    className="traffic-chart"
                    width="640"
                    height="240"
                    ref={accidentProbabilityChartRef}
                  />
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
            <div className="cctv-list" id="cctv-list">
              {cctvs.map((cctv) => (
                <button
                  className={`cctv-item ${cctv.selected ? "is-active" : ""}`}
                  data-index={cctv.index}
                  key={`${cctv.index}-${cctv.name}`}
                  onClick={() => selectCctv(cctv.index)}
                  type="button"
                >
                  <span className="cctv-index">
                    {String(cctv.index + 1).padStart(3, "0")}
                  </span>
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

function normalizeBackendUrl(url) {
  if (!url) return "";
  if (url.startsWith("http://") || url.startsWith("https://")) return url;
  if (!API_URL) return url;
  return `${API_URL}${url}`;
}

function CctvVideoPlayer({ src, fallbackSrc }) {
  const videoRef = useRef(null);
  const [canUseVideo, setCanUseVideo] = useState(Boolean(src));

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !src) return undefined;

    setCanUseVideo(true);
    let hls;
    let destroyed = false;

    async function attachSource() {
      if (video.canPlayType("application/vnd.apple.mpegurl")) {
        video.src = src;
        return;
      }

      const Hls = await loadHls();
      if (destroyed) return;

      if (Hls?.isSupported()) {
        hls = new Hls();
        hls.loadSource(src);
        hls.attachMedia(video);
      } else {
        video.src = src;
      }
    }

    attachSource().catch(() => setCanUseVideo(false));

    return () => {
      destroyed = true;
      if (hls) hls.destroy();
    };
  }, [src]);

  if (!src && fallbackSrc) {
    return <img id="video-feed" src={fallbackSrc} alt="CCTV detection feed" />;
  }

  return (
    <div className="video-player-wrap">
      {canUseVideo ? (
        <video
          id="video-feed"
          ref={videoRef}
          autoPlay
          controls
          muted
          playsInline
          onError={() => setCanUseVideo(false)}
        />
      ) : fallbackSrc ? (
        <img id="video-feed" src={fallbackSrc} alt="CCTV detection feed" />
      ) : (
        <div className="video-placeholder" id="video-feed">
          CCTV 영상 URL을 불러오지 못했습니다.
        </div>
      )}
    </div>
  );
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
    yolo_enabled: false,
    roi_path: API_URL || "NEXT_PUBLIC_API_URL is not set",
    player_url: "",
    cctv_url: "",
    stream_url: "",
  };
}

function loadHls() {
  if (window.Hls) return Promise.resolve(window.Hls);

  return new Promise((resolve, reject) => {
    const existingScript = document.querySelector("script[data-hls-js]");
    if (existingScript) {
      existingScript.addEventListener("load", () => resolve(window.Hls), { once: true });
      existingScript.addEventListener("error", reject, { once: true });
      return;
    }

    const script = document.createElement("script");
    script.src = "https://cdn.jsdelivr.net/npm/hls.js@latest";
    script.async = true;
    script.dataset.hlsJs = "true";
    script.onload = () => resolve(window.Hls);
    script.onerror = reject;
    document.head.appendChild(script);
  });
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
  if (!ctx || !canvas) return;

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

  const lastValue = points[points.length - 1] || 0;
  const lastX = width - padding.right;
  const lastY = padding.top + innerHeight - (Math.min(lastValue, maxValue) / maxValue) * innerHeight;
  ctx.fillStyle = options.lineColor;
  ctx.beginPath();
  ctx.arc(lastX, lastY, 4.5, 0, Math.PI * 2);
  ctx.fill();
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
  drawLineChart(trafficUpChart, trafficUpHistory || [0], {
    lineColor: "#3cf28a",
    fillTop: "rgba(60, 242, 138, 0.32)",
    fillBottom: "rgba(60, 242, 138, 0.02)",
    gridColor: "rgba(160, 184, 220, 0.14)",
    maxFloor: trafficCount + 2,
  });

  drawLineChart(trafficDownChart, trafficDownHistory || [0], {
    lineColor: "#ffae42",
    fillTop: "rgba(255, 174, 66, 0.32)",
    fillBottom: "rgba(255, 174, 66, 0.02)",
    gridColor: "rgba(160, 184, 220, 0.14)",
    maxFloor: trafficCount + 2,
  });

  drawLineChart(accidentProbabilityChart, accidentProbabilityHistory || [0], {
    lineColor: "#ff8a7a",
    fillTop: "rgba(255, 138, 122, 0.34)",
    fillBottom: "rgba(255, 138, 122, 0.03)",
    gridColor: "rgba(160, 184, 220, 0.14)",
    maxFloor: 100,
  });
}
