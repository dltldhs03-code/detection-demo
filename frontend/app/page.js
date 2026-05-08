"use client";

import { useEffect, useMemo, useRef, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL;
const STATUS_REFRESH_INTERVAL_MS = 1000;

const CCTV_ITEMS = [
  "[경부선] 천안호두휴게소",
  "[경부선] 옥산휴게소",
  "[경부선] 남청주육교",
  "[경부선] 청주분기점(고정)",
  "[경부선] 가마육교",
  "[경부선] 금계",
  "[청주영덕선] 문동1",
  "[청주영덕선] 청주분기점",
  "[청주영덕선] 문동2",
  "[청주영덕선] 문의청남대휴게소2",
  "[중부선] 증평2",
  "[중부선] 오창",
  "[중부선] 서청주",
  "[경부선] 남이분기점",
  "[경부선] 속창육교",
  "[경부선] 몽단이고개",
  "[경부선] 수의",
  "[경부선] 죽암교",
  "[경부선] 옥산분기점",
  "[경부선] 강서",
];

export default function HomePage() {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [latestDetection, setLatestDetection] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [history, setHistory] = useState({
    trafficUp: [0],
    trafficDown: [0],
    accidentProbability: [0],
  });

  const trafficUpChartRef = useRef(null);
  const trafficDownChartRef = useRef(null);
  const accidentProbabilityChartRef = useRef(null);

  useEffect(() => {
    let isMounted = true;

    async function refreshStatus() {
      if (!API_URL) {
        if (isMounted) {
          setError("NEXT_PUBLIC_API_URL is not set.");
          setLoading(false);
        }
        return;
      }

      try {
        const response = await fetch(`${API_URL}/api/latest`, { cache: "no-store" });
        if (!response.ok) {
          throw new Error(`Backend returned ${response.status}`);
        }
        const result = await response.json();
        if (isMounted) {
          setLatestDetection(result.data);
          setError("");
          setLoading(false);
        }
      } catch (err) {
        if (isMounted) {
          setError(`Cannot reach backend: ${err.message}`);
          setLoading(false);
        }
      }
    }

    refreshStatus();
    const intervalId = setInterval(refreshStatus, STATUS_REFRESH_INTERVAL_MS);

    return () => {
      isMounted = false;
      clearInterval(intervalId);
    };
  }, []);

  const status = useMemo(() => {
    const confidence = Number(latestDetection?.confidence || 0);
    const trafficCount = latestDetection ? Math.max(1, Math.round(confidence * 10)) : 0;
    const trafficUp = latestDetection ? Math.ceil(trafficCount * 0.55) : 0;
    const trafficDown = latestDetection ? Math.max(0, trafficCount - trafficUp) : 0;
    const imbalance = Math.abs(trafficUp - trafficDown);
    const accidentProbability = latestDetection
      ? Math.min(99, Math.round(12 + trafficCount * 8 + imbalance * 3))
      : 0;

    return {
      selected_index: selectedIndex,
      selected_name: CCTV_ITEMS[selectedIndex],
      stream_status: error ? "연결 오류" : loading ? "준비 중" : "연결됨",
      traffic_count: trafficCount,
      traffic_up: trafficUp,
      traffic_down: trafficDown,
      accident_probability: accidentProbability,
      accident_status: latestDetection ? `${accidentProbability}%` : "-",
      yolo_enabled: Boolean(latestDetection) && !error,
      roi_path: API_URL || "NEXT_PUBLIC_API_URL is not set",
    };
  }, [error, latestDetection, loading, selectedIndex]);

  useEffect(() => {
    setHistory((current) => ({
      trafficUp: appendHistory(current.trafficUp, status.traffic_up),
      trafficDown: appendHistory(current.trafficDown, status.traffic_down),
      accidentProbability: appendHistory(
        current.accidentProbability,
        status.accident_probability,
      ),
    }));
  }, [status.traffic_up, status.traffic_down, status.accident_probability]);

  useEffect(() => {
    renderCharts({
      trafficCount: status.traffic_count,
      trafficUpHistory: history.trafficUp,
      trafficDownHistory: history.trafficDown,
      accidentProbabilityHistory: history.accidentProbability,
      trafficUpChart: trafficUpChartRef.current,
      trafficDownChart: trafficDownChartRef.current,
      accidentProbabilityChart: accidentProbabilityChartRef.current,
    });
  }, [history, status.traffic_count]);

  useEffect(() => {
    function handleResize() {
      renderCharts({
        trafficCount: status.traffic_count,
        trafficUpHistory: history.trafficUp,
        trafficDownHistory: history.trafficDown,
        accidentProbabilityHistory: history.accidentProbability,
        trafficUpChart: trafficUpChartRef.current,
        trafficDownChart: trafficDownChartRef.current,
        accidentProbabilityChart: accidentProbabilityChartRef.current,
      });
    }

    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [history, status.traffic_count]);

  return (
    <main className="page">
      <header className="topbar">
        <div>
          <p className="eyebrow">Selected CCTV</p>
          <h1 id="selected-name">{status.selected_name}</h1>
        </div>
        <div className="status">
          <span className="status-label">Stream Status</span>
          <strong id="stream-status">{status.stream_status}</strong>
          <span
            className={`status-chip ${status.yolo_enabled ? "is-on" : "is-off"}`}
            id="yolo-chip"
          >
            {status.yolo_enabled ? "YOLO ON" : "YOLO OFF"}
          </span>
          <p className="status-meta" id="roi-path">{status.roi_path}</p>
        </div>
      </header>

      <section className="dashboard">
        <section className="left">
          <div className="section-head">
            <h2>Detection Screen</h2>
          </div>
          <div className="video-card">
            <DetectionScreen detection={latestDetection} loading={loading} error={error} />
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
                  <strong id="traffic-count">{status.traffic_count}</strong>
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
                      {status.traffic_down}
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
                      {status.traffic_up}
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
                  {status.accident_status}
                </div>
              </div>

              <div className="accident-body">
                <div className="probability-block">
                  <p className="metric-note">교통량 기반 추정치</p>
                  <div className="probability-value">
                    <strong id="accident-probability">
                      {status.accident_probability}
                    </strong>
                    <span>%</span>
                  </div>
                  <div className="probability-meter">
                    <div
                      className="probability-fill"
                      id="accident-probability-fill"
                      style={{ width: `${status.accident_probability}%` }}
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
              {CCTV_ITEMS.map((name, index) => (
                <button
                  className={`cctv-item ${index === selectedIndex ? "is-active" : ""}`}
                  data-index={index}
                  key={name}
                  onClick={() => setSelectedIndex(index)}
                  type="button"
                >
                  <span className="cctv-index">
                    {String(index + 1).padStart(3, "0")}
                  </span>
                  <span className="cctv-name">{name}</span>
                </button>
              ))}
            </div>
          </div>
        </aside>
      </section>
    </main>
  );
}

function DetectionScreen({ detection, loading, error }) {
  const label = detection
    ? `${detection.class_name} ${Number(detection.confidence).toFixed(2)}`
    : loading
      ? "loading..."
      : error || "No detection data";

  return (
    <div className="video-placeholder" id="video-feed" aria-label="CCTV detection feed">
      <div className="video-placeholder-title">Detection Screen</div>
      <div className="video-placeholder-message">{label}</div>
      {detection && (
        <>
          <div className="demo-bbox">
            <span>{label}</span>
          </div>
          <div className="demo-readout">
            <strong>{detection.class_name}</strong>
            <span>bbox: {JSON.stringify(detection.bbox)}</span>
            <span>{detection.timestamp}</span>
          </div>
        </>
      )}
    </div>
  );
}

function appendHistory(values, nextValue) {
  return [...values.slice(-35), nextValue];
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
    if (index === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
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
    if (index === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
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
