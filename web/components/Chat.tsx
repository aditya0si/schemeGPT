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

type Msg = {
  role: "user" | "assistant";
  text: string;
  streaming?: boolean;
  sources?: Source[];
  quotes?: Quote[];
  mode?: "live" | "demo";
  notice?: string | null;
  error?: string;
};

const PLACEHOLDER: Record<"en" | "hi", string> = {
  en: "Ask anything about Indian government schemes…",
  hi: "भारत सरकार की योजनाओं के बारे में कुछ भी पूछें…",
};

export function Chat() {
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
        patch((a) => ({
          ...a,
          streaming: false,
          error: detail.error ?? `Request failed (${resp.status}).`,
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
            else if (line.startsWith("data: "))
              data = JSON.parse(line.slice(6));
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
          error: "Could not reach SchemeGPT. Check your connection and retry.",
        }));
      else patch((a) => ({ ...a, streaming: false }));
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-16">
      <ul className="space-y-8">
        {messages.map((m, i) =>
          m.role === "user" ? (
            <li key={i} className="border-l-4 border-ink pl-4">
              <p className="whitespace-pre-wrap font-sans text-lg">{m.text}</p>
            </li>
          ) : (
            <li key={i}>
              {m.mode === "demo" ? (
                <div className="bg-ink px-4 py-2 text-paper">
                  <p className="font-mono text-[11px] uppercase">
                    Mode[demo] — pre-made answer, not a live result
                  </p>
                </div>
              ) : null}
              {m.mode === "live" ? (
                <p className="font-mono text-[11px] uppercase text-verified">
                  Mode[live] · Groq RAG
                </p>
              ) : null}
              {m.notice && m.mode !== "demo" ? (
                <p className="font-mono text-[11px] text-ink/60">{m.notice}</p>
              ) : null}
              {m.notice && m.mode === "demo" ? (
                <p className="border-b border-ink/25 pb-2 font-mono text-[11px] text-ink/60">
                  {m.notice}
                </p>
              ) : null}
              <p
                className={`whitespace-pre-wrap py-3 font-sans text-lg leading-relaxed ${
                  m.streaming ? "caret" : ""
                }`}
              >
                {m.text}
              </p>
              {m.error ? (
                <p className="border border-signal px-3 py-2 font-mono text-[11px] uppercase text-signal">
                  {m.error}{" "}
                  <button
                    type="button"
                    className="underline"
                    onClick={() => ask(messages[i - 1]?.text ?? "")}
                  >
                    retry ↻
                  </button>
                </p>
              ) : null}
              {m.sources && m.sources.length > 0 && !m.streaming ? (
                <div className="mt-2 border border-ink/25 px-4 py-2">
                  <p className="pt-1 font-mono text-[11px] uppercase">
                    Sources[{m.sources.length}]
                  </p>
                  <ul>
                    {m.sources.map((s, j) => (
                      <SourceCard key={j} source={s} />
                    ))}
                  </ul>
                </div>
              ) : null}
              {m.quotes && m.quotes.length > 0 && !m.streaming ? (
                <div className="mt-2 border border-ink/25 px-4 py-3">
                  <p className="font-mono text-[11px] uppercase">
                    Verified quotes[{m.quotes.length}]
                  </p>
                  <ul className="mt-2 space-y-3">
                    {m.quotes.map((q, j) => (
                      <li key={j} className="border-l-2 border-ink/25 pl-3">
                        {q.verified ? (
                          <span className="font-mono text-[11px] uppercase text-verified">
                            ✓ verified
                          </span>
                        ) : (
                          <span className="font-mono text-[11px] uppercase text-signal">
                            ✗ unverified
                          </span>
                        )}{" "}
                        <span className="font-mono text-[11px] text-ink/60">
                          {q.matched_source ?? q.source}
                        </span>
                        <blockquote className="mt-1 font-sans text-base italic text-ink">
                          “{q.text}”
                        </blockquote>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </li>
          ),
        )}
      </ul>

      <form
        className="mt-10 flex items-stretch border border-ink"
        onSubmit={(e) => {
          e.preventDefault();
          ask(input);
        }}
      >
        <span aria-hidden="true" className="grid place-items-center bg-ink px-3 font-mono text-paper">
          &gt;
        </span>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={PLACEHOLDER[lang]}
          className="w-full bg-paper px-4 py-4 font-sans text-lg outline-none placeholder:text-ink/40"
          maxLength={2000}
          minLength={2}
          required
          aria-label="Question"
        />
        {busy ? (
          <button
            type="button"
            onClick={() => abortRef.current?.abort()}
            className="bg-ink px-5 font-mono text-xs uppercase text-paper"
          >
            Stop
          </button>
        ) : (
          <button
            type="submit"
            className="bg-ink px-5 font-mono text-xs uppercase text-paper hover:bg-verified focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink"
          >
            Ask
          </button>
        )}
      </form>
      <p className="mt-3 font-mono text-[11px] uppercase text-ink/50">
        Not official advice — verify on official sources before applying
      </p>
    </div>
  );
}
