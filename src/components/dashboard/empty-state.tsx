export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-xl border border-dashed border-zinc-700 bg-zinc-900/30 p-4 text-sm">
      <p className="font-medium text-zinc-200">{title}</p>
      <p className="mt-1 text-zinc-500">{description}</p>
    </div>
  );
}
