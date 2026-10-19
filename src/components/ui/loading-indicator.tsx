export function LoadingIndicator({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-zinc-400" role="status" aria-live="polite">
      <span className="h-2 w-2 animate-ping rounded-full bg-indigo-400" />
      {label}
    </div>
  );
}
