import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin", "cyrillic"],
});

export const metadata: Metadata = {
  title: "Каспийский диспетчер",
  description: "Окно логиста коридора «Север–Юг»: карта, цифровые двойники грузов, прогноз задержек",
  icons: { icon: [{ url: "/logo-mark.png", type: "image/png" }] },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ru" className={`${inter.variable} h-full`}>
      <body className="h-full overflow-auto">{children}</body>
    </html>
  );
}
