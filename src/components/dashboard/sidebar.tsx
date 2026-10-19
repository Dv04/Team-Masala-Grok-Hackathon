export function Sidebar() {
  return (
    <aside className="hidden w-64 border-r border-zinc-800 bg-zinc-950/70 p-4 lg:block">
      <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-zinc-400">GrokBot Starter</h2>
      <ul className="space-y-2 text-sm text-zinc-300">
        <li className="rounded-md bg-zinc-800 px-3 py-2">Dashboard</li>
        <li className="rounded-md px-3 py-2 text-zinc-500">Agents</li>
        <li className="rounded-md px-3 py-2 text-zinc-500">Workflows</li>
        <li className="rounded-md px-3 py-2 text-zinc-500">Tools</li>
      </ul>
    </aside>
  );
}
