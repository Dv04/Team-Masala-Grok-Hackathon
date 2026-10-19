export function Navigation() {
  return (
    <header className="sticky top-0 z-20 flex items-center justify-between border-b border-zinc-800 bg-zinc-950/90 px-4 py-3 backdrop-blur">
      <div>
        <h1 className="text-lg font-semibold text-zinc-100">GrokBot Hackathon Starter</h1>
        <p className="text-xs text-zinc-400">LOCAL MOCK workflow mode</p>
      </div>
      <span className="rounded-full border border-zinc-700 px-3 py-1 text-xs text-zinc-300">
        Ready for rapid challenge adaptation
      </span>
    </header>
  );
}
