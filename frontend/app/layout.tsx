import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "AI Home-Lab Operator",
  description: "Private infrastructure investigations, grounded in evidence.",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
