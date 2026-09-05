import type { Metadata } from "next";
import Script from "next/script";
import { Providers } from "@/components/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Governance Control Plane Studio",
  description: "Governance studio for AI Governance Control Plane APIs.",
  icons: {
    icon: "/favicon.ico",
    apple: "/apple-icon.png",
  },
};

export default function RootLayout({
  children,
  executionPicker,
  executionInspector,
  reconciliationResults,
}: Readonly<{
  children: React.ReactNode;
  executionPicker?: React.ReactNode;
  executionInspector?: React.ReactNode;
  reconciliationResults?: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        <Script src="/runtime-config.js" strategy="beforeInteractive" />
      </head>
      <body>
        <Providers>{children}{executionPicker}{executionInspector}{reconciliationResults}</Providers>
      </body>
    </html>
  );
}
