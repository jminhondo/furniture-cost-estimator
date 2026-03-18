import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Estimador de Costos — Muebles a Medida",
  description: "Sistema de estimación de costos de fabricación e instalación de muebles",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body className={`${inter.className} min-h-screen flex flex-col`}>
        {/* ── Navbar ────────────────────────────────────────────────── */}
        <header className="bg-white border-b border-gray-200 sticky top-0 z-50">
          <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
            <Link href="/" className="flex items-center gap-2 font-semibold text-gray-900 hover:text-blue-600">
              <span className="text-xl">🪑</span>
              <span>Estimador de Costos</span>
            </Link>
            <nav className="flex items-center gap-6 text-sm text-gray-600">
              <Link href="/" className="hover:text-blue-600">Nueva estimación</Link>
              <a
                href="/api/docs"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-blue-600"
              >
                API docs
              </a>
            </nav>
          </div>
        </header>

        {/* ── Page content ──────────────────────────────────────────── */}
        <main className="flex-1 max-w-6xl mx-auto w-full px-4 py-8">
          {children}
        </main>

        {/* ── Footer ────────────────────────────────────────────────── */}
        <footer className="border-t border-gray-200 text-center text-xs text-gray-400 py-4">
          Furniture Cost Estimator · Mi Carpintería S.R.L.
        </footer>
      </body>
    </html>
  );
}
