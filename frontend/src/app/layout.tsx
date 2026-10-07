import type { Metadata } from "next";
import "./globals.css";
import { AppShell } from "@/components/layout/AppShell";
export const metadata: Metadata = {
  title: "PeCal Pulse · Sales workspace",
  description:
    "Mock sales-assistant workspace for the Perschmann calibration hackathon.",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
