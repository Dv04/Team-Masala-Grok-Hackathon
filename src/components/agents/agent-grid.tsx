import { AgentCard } from "@/components/dashboard/agent-card";

interface AgentSummary {
  id: string;
  role: string;
  description: string;
  provider: string;
}

export function AgentGrid({ agents }: { agents: AgentSummary[] }) {
  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold text-zinc-100">Configured agents</h2>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {agents.map((agent) => (
          <AgentCard key={agent.id} agent={agent} />
        ))}
      </div>
    </section>
  );
}
