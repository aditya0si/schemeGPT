"use client";

import { useLanguage } from "./LanguageProvider";

function LangSwitch() {
  const { lang, setLang } = useLanguage();
  return (
    <button
      type="button"
      onClick={() => setLang(lang === "en" ? "hi" : "en")}
      className="font-mono text-xs uppercase tracking-wide focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink"
      aria-label="Toggle language"
    >
      LANG[{lang === "en" ? "EN" : "HI"}] ↻
    </button>
  );
}

export function HeaderChrome() {
  return (
    <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-ink px-4 py-4 lg:px-14">
      <a
        href="/"
        className="font-sans text-lg font-extrabold uppercase tracking-tight focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink"
      >
        SchemeGPT
      </a>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        <nav aria-label="Site" className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <a
            href="/evidence"
            data-testid="nav-evidence"
            className="font-mono text-xs uppercase tracking-wide underline decoration-1 underline-offset-4 hover:text-verified focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink"
          >
            Evidence
          </a>
          <a
            href="/coverage"
            data-testid="nav-coverage"
            className="font-mono text-xs uppercase tracking-wide underline decoration-1 underline-offset-4 hover:text-verified focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink"
          >
            Coverage
          </a>
        </nav>
        <span className="hidden font-mono text-xs uppercase sm:inline">
          MODE[—]
        </span>
        <LangSwitch />
      </div>
    </header>
  );
}

export function FooterChrome() {
  return (
    <footer className="bg-ink px-4 py-6 text-paper lg:px-14">
      <p className="font-mono text-[11px] uppercase leading-relaxed">
        SchemeGPT (C) 2026 · 28.6139 N X 77.2090 E · Not official advice —
        verify on official sources
      </p>
    </footer>
  );
}
