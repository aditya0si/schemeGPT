export default function CoverageLoading() {
  return (
    <div
      className="mx-auto w-full max-w-4xl px-4 py-12 lg:px-0"
      aria-busy="true"
      role="status"
      data-testid="coverage-loading"
    >
      <p className="font-mono text-xs uppercase tracking-wider text-ink/70">
        Coverage · reading the catalog
      </p>
      <h1 className="mt-3 font-sans text-4xl font-bold uppercase leading-tight tracking-tight sm:text-5xl">
        Loading coverage…
      </h1>
      <p className="mt-5 max-w-2xl font-sans text-lg leading-relaxed text-ink/90">
        Asking the configured API for its coverage report. On a free-tier
        instance this can take a few seconds while the service wakes up.
      </p>
    </div>
  );
}
