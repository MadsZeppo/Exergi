import { ClerkProvider } from "@clerk/nextjs";
import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "Exergi - Know what to do next",
  description: "See the likely commercial outcome before you act.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body><ClerkProvider>{children}</ClerkProvider></body>
    </html>
  );
}
