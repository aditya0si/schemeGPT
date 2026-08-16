export function StaggeredText({ text }: { text: string }) {
  const letters = Array.from(text);
  return (
    <span className="letter-stagger" aria-label={text} role="text">
      {letters.map((ch, i) => (
        <span key={i} aria-hidden="true" style={{ animationDelay: `${i * 28}ms` }}>
          {ch === " " ? "\u00A0" : ch}
        </span>
      ))}
    </span>
  );
}
