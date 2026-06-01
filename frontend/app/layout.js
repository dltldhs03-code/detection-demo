import "./globals.css";

export const metadata = {
  title: "CCTV Monitor",
  description: "CCTV object detection monitoring dashboard",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body style={{ margin: 0 }}>{children}</body>
    </html>
  );
}
