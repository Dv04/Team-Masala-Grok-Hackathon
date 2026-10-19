import { Navigation } from "@/components/dashboard/navigation";
import { Sidebar } from "@/components/dashboard/sidebar";
import { DashboardShell } from "@/components/dashboard/dashboard-shell";

export default function HomePage() {
  return (
    <div className="min-h-screen bg-zinc-950">
      <Navigation />
      <div className="mx-auto flex max-w-[1400px]">
        <Sidebar />
        <main className="flex-1">
          <DashboardShell />
        </main>
      </div>
    </div>
  );
}
