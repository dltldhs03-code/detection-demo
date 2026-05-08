"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL;

export default function HomePage() {
  const [latestDetection, setLatestDetection] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let isMounted = true;

    async function fetchLatestDetection() {
      if (!API_URL) {
        if (isMounted) {
          setError("NEXT_PUBLIC_API_URL is not set.");
          setLoading(false);
        }
        return;
      }

      try {
        const response = await fetch(`${API_URL}/api/latest`, {
          cache: "no-store",
        });

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

    fetchLatestDetection();
    const intervalId = setInterval(fetchLatestDetection, 1000);

    return () => {
      isMounted = false;
      clearInterval(intervalId);
    };
  }, []);

  return (
    <main style={styles.page}>
      <section style={styles.panel}>
        <div style={styles.header}>
          <div>
            <h1 style={styles.title}>Jetson Nano Detection Dashboard</h1>
            <p style={styles.subtitle}>
              Latest simulated object detection result from the Railway backend
            </p>
          </div>
          <div style={error ? styles.statusError : styles.statusOk}>
            {error ? "Offline" : "Online"}
          </div>
        </div>

        {loading && <div style={styles.message}>Loading latest detection...</div>}

        {!loading && error && (
          <div style={styles.errorBox}>
            <strong>Error</strong>
            <p style={styles.errorText}>{error}</p>
          </div>
        )}

        {!loading && !error && !latestDetection && (
          <div style={styles.message}>
            No detection data yet. Send fake data with curl or the Python test
            client.
          </div>
        )}

        {!loading && !error && latestDetection && (
          <div style={styles.grid}>
            <InfoCard label="Class Name" value={latestDetection.class_name} />
            <InfoCard
              label="Confidence"
              value={Number(latestDetection.confidence).toFixed(2)}
            />
            <InfoCard
              label="Bounding Box"
              value={JSON.stringify(latestDetection.bbox)}
            />
            <InfoCard label="Timestamp" value={latestDetection.timestamp} />
          </div>
        )}
      </section>
    </main>
  );
}

function InfoCard({ label, value }) {
  return (
    <div style={styles.card}>
      <div style={styles.label}>{label}</div>
      <div style={styles.value}>{value}</div>
    </div>
  );
}

const styles = {
  page: {
    minHeight: "100vh",
    background: "#f3f6fa",
    color: "#172033",
    fontFamily:
      'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    padding: "32px",
    boxSizing: "border-box",
  },
  panel: {
    width: "100%",
    maxWidth: "920px",
    margin: "0 auto",
    background: "#ffffff",
    border: "1px solid #d9e1ea",
    borderRadius: "8px",
    padding: "28px",
    boxSizing: "border-box",
    boxShadow: "0 12px 30px rgba(20, 31, 48, 0.08)",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    gap: "16px",
    alignItems: "flex-start",
    marginBottom: "24px",
  },
  title: {
    margin: "0 0 8px",
    fontSize: "28px",
    lineHeight: 1.2,
  },
  subtitle: {
    margin: 0,
    color: "#617086",
    fontSize: "15px",
  },
  statusOk: {
    background: "#e7f7ee",
    color: "#13733b",
    border: "1px solid #b9e7cc",
    borderRadius: "999px",
    padding: "6px 12px",
    fontSize: "14px",
    fontWeight: 700,
  },
  statusError: {
    background: "#fdecec",
    color: "#b42318",
    border: "1px solid #fac5c5",
    borderRadius: "999px",
    padding: "6px 12px",
    fontSize: "14px",
    fontWeight: 700,
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
    gap: "16px",
  },
  card: {
    border: "1px solid #e1e7ef",
    borderRadius: "8px",
    padding: "18px",
    background: "#fbfcfe",
  },
  label: {
    color: "#64748b",
    fontSize: "13px",
    fontWeight: 700,
    marginBottom: "8px",
    textTransform: "uppercase",
  },
  value: {
    fontSize: "18px",
    fontWeight: 700,
    overflowWrap: "anywhere",
  },
  message: {
    border: "1px dashed #bac7d5",
    borderRadius: "8px",
    padding: "18px",
    color: "#526176",
    background: "#fbfcfe",
  },
  errorBox: {
    border: "1px solid #fac5c5",
    borderRadius: "8px",
    padding: "18px",
    color: "#8a1f17",
    background: "#fff7f7",
  },
  errorText: {
    margin: "8px 0 0",
  },
};
