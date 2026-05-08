export const metadata = {
  title: "Jetson Detection Dashboard Demo",
  description: "A simple dashboard for simulated Jetson Nano object detection results",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body style={{ margin: 0 }}>{children}</body>
    </html>
  );
}
