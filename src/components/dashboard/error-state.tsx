export function ErrorState({ error }: { error: string }) {
  return (
    <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200" role="alert">
      {error}
    </div>
  );
}
