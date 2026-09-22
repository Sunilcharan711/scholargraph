import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "ScholarGraph | Research workspace", description: "Explore papers. Follow the evidence." };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
