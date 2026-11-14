import type { Metadata } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";

import { AppShell } from "@/components/shell/app-shell";
import { Providers } from "@/components/shell/providers";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Ghostwatch", template: "%s · Ghostwatch" },
  description: "Your agents say they're working. Ghostwatch makes sure they actually are.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`dark ${GeistSans.variable} ${GeistMono.variable} h-full antialiased`}>
      <body className="h-full overflow-hidden">
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
