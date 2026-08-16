import type { Metadata } from "next";
import { Archivo, Martian_Mono, Noto_Sans_Devanagari } from "next/font/google";
import "./globals.css";

const archivo = Archivo({
  subsets: ["latin"],
  variable: "--font-archivo",
});
const martian = Martian_Mono({
  subsets: ["latin"],
  variable: "--font-martian",
});
const devanagari = Noto_Sans_Devanagari({
  subsets: ["devanagari"],
  variable: "--font-devanagari",
});

export const metadata: Metadata = {
  title: "SchemeGPT — Indian schemes, answered honestly",
  description:
    "Ask questions about Indian government schemes in any language. Answers quote the exact policy statements they rely on.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body
        className={`${archivo.variable} ${martian.variable} ${devanagari.variable} bg-paper text-ink font-sans antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
