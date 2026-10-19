interface AgentSummary {
  id: string;
  role: string;
  description: string;
  provider: string;
}

export function AgentCard({ agent }: { agent: AgentSummary }) {
  return (
    <article className="rounded-xl border border-zinc-800 bg-zinc-900/70 p-3">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-100">{agent.role}</h3>
        <span className="rounded-full bg-zinc-800 px-2 py-1 text-[11px] text-zinc-300">{agent.provider}</span>
      </div>
      <p className="text-xs text-zinc-400">{agent.description}</p>
      <p className="mt-2 text-[11px] text-zinc-500">{agent.id}</p>
    </article>
  );
}
