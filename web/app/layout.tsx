import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "가온교회 주일예배 슬라이드",
  description: "매주 주일예배 슬라이드 입력 폼",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body className="bg-stone-50 text-stone-900 antialiased">
        {children}
      </body>
    </html>
  );
}
