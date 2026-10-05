"use client";

import { useRef, useState } from "react";
import { useLanguage } from "./LanguageProvider";
import { SourceCard, type Source } from "./SourceCard";

type Quote = {
  text: string;
  source: string;
  status?: string | null;
  verified: boolean;
  matched_source?: string | null;
};

type Step = { tool: string; summary: string };

type Msg = {
  role: "user" | "assistant";
  text: string;
  streaming?: boolean;
  sources?: Source[];
  quotes?: Quote[];
  steps?: Step[];
  mode?: "live" | "demo";
  notice?: string | null;
  error?: string;
  feedback?: "up" | "down" | "sent";
};

const PLACEHOLDER: Record<"en" | "hi", string> = {
  en: "Ask anything about Indian government schemes…",
  hi: "भारत सरकार की योजनाओं के बारे में कुछ भी पूछें…",
};

const EXAMPLE_QUESTIONS: Record<"en" | "hi", { label: string; query: string }[]> = {
  en: [
    {
      label: "PM-KISAN",
      query: "How much income support does PM-KISAN provide?",
    },
    {
      label: "Ayushman Bharat",
      query: "Who is covered under Ayushman Bharat PM-JAY?",
    },
    {
      label: "PMAY-G",
      query: "What financial assistance is given under PMAY-G rural housing?",
    },
    {
      label: "Startup India",
      query: "What are the eligibility criteria for Startup India?",
    },
  ],
  hi: [
    {
      label: "पीएम-किसान",
      query: "पीएम-किसान योजना में कितनी राशि मिलती है?",
    },
    {
      label: "आयुष्मान भारत",
      query: "आयुष्मान भारत योजना के तहत किसे कवर किया गया है?",
    },
    {
      label: "पीएम आवास योजना",
      query: "पीएम आवास योजना - ग्रामीण में कितनी सहायता मिलती है?",
    },
    {
      label: "स्टार्टअप इंडिया",
      query: "स्टार्टअप इंडिया के लिए क्या पात्रता मानदंड हैं?",
    },
  ],
};

export function Chat({ initialApiReachable = true }: { initialApiReachable?: boolean }) {
  const { lang } = useLanguage();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  async function ask(question: string) {
    if (!question.trim() || busy) return;
    setBusy(true);
    setInput("");
    const controller = new AbortController();
    abortRef.current = controller;
    setMessages((m) => [
      ...m,
      { role: "user", text: question },
      { role: "assistant", text: "", streaming: true, sources: [] },
    ]);

    const patch = (fn: (a: Msg) => Msg) =>
      setMessages((m) => {
        const copy = [...m];
        const last = copy.length - 1;
        copy[last] = fn(copy[last]);
        return copy;
      });

    try {
      const resp = await fetch("/api/chat/stream", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ question, language: lang }),
        signal: controller.signal,
      });
      if (!resp.ok || !resp.body) {
        const detail = await resp
          .json()
          .catch(() => ({ error: "Request failed." }));
        const errorMessage =
          resp.status === 502
            ? (detail.error ||
                "The SchemeGPT API is unreachable. If running on Render free tier, the service may be spinning up — please wait 30 seconds and retry.")
            : (detail.error ?? `Request failed (${resp.status}).`);
        patch((a) => ({
          ...a,
          streaming: false,
          error: errorMessage,
        }));
        return;
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const blocks = buf.split("\n\n");
        buf = blocks.pop() ?? "";
        for (const block of blocks) {
          let event = "";
          let data: Record<string, unknown> | unknown[] | null = null;
          for (const line of block.split("\n")) {
            if (line.startsWith("event: ")) event = line.slice(7);
            else if (line.startsWith("data: ")) {
              try {
                data = JSON.parse(line.slice(6));
              } catch {
                data = null;
              }
            }
          }
          if (event === "sources")
            patch((a) => ({ ...a, sources: data as Source[] }));
          else if (event === "token")
            patch((a) => ({ ...a, text: a.text + (data as { text: string }).text }));
          else if (event === "done")
            patch((a) => ({
              ...a,
              streaming: false,
              mode: (data as { mode: "live" | "demo" }).mode,
              notice: (data as { notice: string | null }).notice,
            }));
          else if (event === "quotes")
            patch((a) => ({ ...a, quotes: data as Quote[] }));
          else if (event === "step")
            patch((a) => ({
              ...a,
              steps: [...(a.steps ?? []), data as Step],
            }));
          else if (event === "error")
            patch((a) => ({
              ...a,
              streaming: false,
              error: (data as { message: string }).message,
            }));
        }
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError")
        patch((a) => ({
          ...a,
          streaming: false,
          error:
            "Could not reach SchemeGPT API. Check your connection or wait 30 seconds if the free tier container is starting up.",
        }));
      else patch((a) => ({ ...a, streaming: false }));
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }

  async function sendFeedback(i: number, rating: "up" | "down") {
    const assistant = messages[i];
    const question = messages[i - 1]?.text ?? "";
    patchIndex(i, (a) => ({ ...a, feedback: "sent" }));
    try {
      await fetch("/api/chat/feedback", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          question,
          answer: assistant.text,
          rating,
          language: lang,
        }),
      });
    } catch {
      // Feedback is best-effort; never disturb the conversation.
    }
  }

  const patchIndex = (index: number, fn: (a: Msg) => Msg) =>
    setMessages((m) => {
      const copy = [...m];
      copy[index] = fn(copy[index]);
      return copy;
    });

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-16">
      <ul className="space-y-8">
        {messages.map((m, i) =>
          m.role === "user" ? (
            <li key={i} className="border-l-4 border-ink pl-4 py-1">
              <p className="whitespace-pre-wrap font-sans text-lg font-medium text-ink">
                {m.text}
              </p>
            </li>
          ) : (
            <li key={i} className="space-y-3">
              {m.streaming ? (
                <div className="inline-flex items-center gap-2 border border-ink/30 bg-paper-dim px-3 py-1 text-ink">
                  <span className="inline-block h-2 w-2 animate-pulse bg-live" aria-hidden="true" />
                  <span className="font-mono text-[11px] font-bold uppercase tracking-wider">
                    Searching policy corpus &amp; generating answer...
                  </span>
                </div>
              ) : null}

              {!m.streaming && m.mode === "demo" ? (
                <div className="inline-flex items-center gap-2 border border-ink bg-paper-dim px-3 py-1.5 text-ink">
                  <span className="inline-block h-2 w-2 bg-signal" aria-hidden="true" />
                  <span className="font-mono text-[11px] font-bold uppercase tracking-wider">
                    Demo mode — no live model key configured
                  </span>
                </div>
              ) : null}

              {!m.streaming && m.mode === "live" ? (
                <div className="inline-flex items-center gap-2 border border-verified/50 bg-paper px-3 py-1.5 text-verified">
                  <span className="inline-block h-2 w-2 bg-verified" aria-hidden="true" />
                  <span className="font-mono text-[11px] font-bold uppercase tracking-wider">
                    Live mode · Groq RAG
                  </span>
                </div>
              ) : null}

              {m.notice ? (
                <p className="border-l-2 border-ink/20 pl-2.5 font-mono text-xs text-ink/70 leading-relaxed">
                  {m.notice}
                </p>
              ) : null}

              {m.steps && m.steps.length > 0 ? (
                <div className="border border-ink/15 bg-paper-dim/60 px-3 py-2">
                  <p className="font-mono text-[10px] font-bold uppercase tracking-wider text-ink/50">
                    Execution Pipeline
                  </p>
                  <ul className="mt-1 space-y-1">
                    {m.steps.map((s, j) => (
                      <li key={j} className="font-mono text-[11px] text-ink/75">
                        ⇄ <span className="font-bold text-ink">{s.tool}</span> — {s.summary}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {m.text ? (
                <p
                  className={`whitespace-pre-wrap py-2 font-sans text-lg leading-relaxed text-ink ${
                    m.streaming ? "caret" : ""
                  }`}
                >
                  {m.text}
                </p>
              ) : null}

              {m.error ? (
                <div className="border-2 border-signal bg-paper p-4">
                  <div className="flex items-start gap-3">
                    <span
                      className="font-mono text-base font-bold text-signal select-none"
                      aria-hidden="true"
                    >
                      [!]
                    </span>
                    <div className="space-y-2">
                      <p className="font-mono text-xs font-bold uppercase tracking-wider text-signal">
                        Service Notice / Error
                      </p>
                      <p className="font-sans text-sm leading-relaxed text-ink/90">
                        {m.error}
                      </p>
                      <div>
                        <button
                          type="button"
                          className="inline-flex items-center gap-1.5 border border-ink bg-ink px-4 py-1.5 font-mono text-xs uppercase text-paper hover:bg-verified hover:border-verified transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink"
                          onClick={() => ask(messages[i - 1]?.text ?? "")}
                        >
                          Retry question ↻
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              ) : null}

              {m.quotes && m.quotes.length > 0 && !m.streaming ? (
                <div className="mt-4 border-2 border-ink/25 bg-paper p-4">
                  <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-ink/20 pb-2">
                    <p className="font-mono text-xs font-bold uppercase tracking-wider text-ink">
                      Verified source quotes [{m.quotes.length}]
                    </p>
                    <span className="font-mono text-[10px] uppercase text-ink/60">
                      Exact policy citations
                    </span>
                  </div>
                  <ul className="mt-3 space-y-3">
                    {m.quotes.map((q, j) => {
                      const rawSource = q.matched_source ?? q.source ?? "official source";
                      const filename = rawSource.split("/").pop() ?? rawSource;
                      const schemeSlug = filename.replace(/\.(md|json)$/i, "");
                      const schemeTitle = schemeSlug
                        .split(/[-_]/)
                        .map((word) => word.toUpperCase())
                        .join(" ");

                      return (
                        <li key={j} className="border-l-3 border-ink pl-3 py-1">
                          <div className="flex flex-wrap items-center gap-2">
                            {q.verified ? (
                              <span className="inline-flex items-center gap-1 font-mono text-[11px] font-bold uppercase text-verified">
                                <span>✓</span> Verified Quote
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 font-mono text-[11px] font-bold uppercase text-signal">
                                <span>✗</span> Unverified
                              </span>
                            )}
                            <span className="font-mono text-[11px] text-ink/30">|</span>
                            <span className="font-mono text-[11px] font-bold uppercase text-ink">
                              Scheme: {schemeTitle}
                            </span>
                            <span className="font-mono text-[10px] text-ink/50">
                              ({filename})
                            </span>
                          </div>
                          <blockquote className="mt-2 font-sans text-base italic text-ink/90">
                            “{q.text}”
                          </blockquote>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ) : null}

              {m.sources && m.sources.length > 0 && !m.streaming ? (
                <div className="mt-3 border border-ink/20 bg-paper p-4">
                  <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-ink/15 pb-2">
                    <p className="font-mono text-xs font-bold uppercase tracking-wider text-ink">
                      Retrieved sources [{m.sources.length}]
                    </p>
                    <span className="font-mono text-[10px] uppercase text-ink/50">
                      Corpus provenance
                    </span>
                  </div>
                  <ul className="mt-1 divide-y divide-ink/10">
                    {m.sources.map((s, j) => (
                      <SourceCard key={j} source={s} />
                    ))}
                  </ul>
                </div>
              ) : null}

              {m.mode && !m.streaming && m.text ? (
                <div className="mt-2 pt-2 border-t border-ink/15 flex items-center justify-between text-ink/60 font-mono text-[11px] uppercase">
                  {m.feedback === "sent" ? (
                    <span className="text-verified">Feedback recorded — thank you</span>
                  ) : (
                    <div className="flex items-center gap-4">
                      <span>Was this helpful?</span>
                      <button
                        type="button"
                        className="hover:text-verified hover:underline flex items-center gap-1 focus-visible:outline focus-visible:outline-1 focus-visible:outline-ink"
                        onClick={() => sendFeedback(i, "up")}
                        aria-label="Helpful"
                      >
                        ▲ helpful
                      </button>
                      <button
                        type="button"
                        className="hover:text-signal hover:underline flex items-center gap-1 focus-visible:outline focus-visible:outline-1 focus-visible:outline-ink"
                        onClick={() => sendFeedback(i, "down")}
                        aria-label="Not helpful"
                      >
                        ▼ not helpful
                      </button>
                    </div>
                  )}
                </div>
              ) : null}
            </li>
          ),
        )}
      </ul>

      <div className="mt-10">
        {messages.length === 0 ? (
          <div className="mb-8 border border-ink/20 bg-paper-dim/40 p-5">
            <p className="font-mono text-xs font-bold uppercase tracking-wider text-ink/70">
              {lang === "hi" ? "सुझाए गए प्रश्न (क्लिक करके पूछें):" : "Sample queries (click to run):"}
            </p>
            <div className="mt-3 grid grid-cols-1 gap-2.5 sm:grid-cols-2">
              {EXAMPLE_QUESTIONS[lang].map((item, idx) => (
                <button
                  key={idx}
                  type="button"
                  disabled={busy}
                  onClick={() => ask(item.query)}
                  className="group flex flex-col items-start border border-ink/25 bg-paper p-3 text-left hover:border-ink hover:bg-paper-dim focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink transition-colors disabled:opacity-50"
                >
                  <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-ink/60 group-hover:text-ink">
                    [{item.label}]
                  </span>
                  <span className="mt-1 font-sans text-sm text-ink/90 group-hover:text-ink">
                    {item.query}
                  </span>
                </button>
              ))}
            </div>
          </div>
        ) : null}

        <form
          className="relative flex items-stretch border-2 border-ink bg-paper shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] focus-within:ring-2 focus-within:ring-ink"
          onSubmit={(e) => {
            e.preventDefault();
            ask(input);
          }}
        >
          <span
            aria-hidden="true"
            className="grid place-items-center bg-ink px-3.5 font-mono text-base font-bold text-paper select-none"
          >
            &gt;
          </span>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={PLACEHOLDER[lang]}
            className="w-full bg-paper px-4 py-4 font-sans text-base sm:text-lg text-ink outline-none placeholder:text-ink/40"
            maxLength={2000}
            minLength={2}
            disabled={busy}
            required
            aria-label="Question"
          />
          {busy ? (
            <button
              type="button"
              onClick={() => abortRef.current?.abort()}
              className="bg-signal px-5 font-mono text-xs font-bold uppercase text-paper hover:bg-signal/90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink transition-colors"
            >
              Stop
            </button>
          ) : (
            <button
              type="submit"
              disabled={!input.trim()}
              className="bg-ink px-5 sm:px-6 font-mono text-xs font-bold uppercase text-paper hover:bg-verified focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink transition-colors disabled:opacity-50 disabled:hover:bg-ink"
            >
              Ask →
            </button>
          )}
        </form>

        <p className="mt-3 font-mono text-[11px] uppercase text-ink/50">
          Not official advice — verify on official sources before applying
        </p>
      </div>
    </div>
  );
}
