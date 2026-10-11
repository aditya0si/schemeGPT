import { Fragment } from "react";

export function StaggeredText({ text }: { text: string }) {
  const words = text.split(" ");
  let charIndex = 0;
  return (
    <span className="letter-stagger" aria-label={text} role="text">
      {words.map((word, wi) => {
        const letters = Array.from(word);
        const start = charIndex;
        charIndex += letters.length + 1;
        return (
          <Fragment key={wi}>
            {wi > 0 ? " " : null}
            <span className="letter-word" aria-hidden="true">
              {letters.map((ch, i) => (
                <span
                  key={i}
                  className="letter"
                  aria-hidden="true"
                  style={{ animationDelay: `${(start + i) * 28}ms` }}
                >
                  {ch}
                </span>
              ))}
            </span>
          </Fragment>
        );
      })}
    </span>
  );
}
