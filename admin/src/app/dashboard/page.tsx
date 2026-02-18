"use client";

import { useEffect, useState } from "react";
import { AdminShell } from "@/components/admin-shell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface Stats {
  total_measurements: number;
  avg_confidence: number | null;
  last_7_days: number;
  by_finger: { finger: string; count: number; avg_confidence: number }[];
  size_distribution: { mapped_size: number; count: number }[];
}

export default function DashboardPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [sizesCount, setSizesCount] = useState(0);
  const [rulesCount, setRulesCount] = useState(0);
  const [setsCount, setSetsCount] = useState(0);

  useEffect(() => {
    fetch("/api/measurements/stats").then((r) => r.json()).then(setStats);
    fetch("/api/sizes").then((r) => r.json()).then((d) => setSizesCount(d.length));
    fetch("/api/rules").then((r) => r.json()).then((d) => setRulesCount(d.length));
    fetch("/api/sets").then((r) => r.json()).then((d) => setSetsCount(d.length));
  }, []);

  return (
    <AdminShell>
      <h1 className="text-2xl font-bold mb-6">Dashboard</h1>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard title="Total Measurements" value={stats?.total_measurements ?? "—"} />
        <StatCard title="Avg Confidence" value={stats?.avg_confidence != null ? `${(stats.avg_confidence * 100).toFixed(0)}%` : "—"} />
        <StatCard title="Last 7 Days" value={stats?.last_7_days ?? "—"} />
        <StatCard title="Sizes / Rules / Sets" value={`${sizesCount} / ${rulesCount} / ${setsCount}`} />
      </div>

      {stats && stats.by_finger.length > 0 && (
        <Card className="mb-6">
          <CardHeader><CardTitle>Measurements by Finger</CardTitle></CardHeader>
          <CardContent>
            <div className="grid grid-cols-5 gap-4">
              {stats.by_finger.map((f) => (
                <div key={f.finger} className="text-center">
                  <div className="text-2xl font-bold">{f.count}</div>
                  <div className="text-sm text-zinc-500 capitalize">{f.finger}</div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {stats && stats.size_distribution.length > 0 && (
        <Card>
          <CardHeader><CardTitle>Size Distribution</CardTitle></CardHeader>
          <CardContent>
            <div className="flex gap-2 items-end h-32">
              {stats.size_distribution.map((s) => {
                const max = Math.max(...stats.size_distribution.map((x) => x.count));
                const h = max > 0 ? (s.count / max) * 100 : 0;
                return (
                  <div key={s.mapped_size} className="flex-1 flex flex-col items-center">
                    <div className="text-xs mb-1">{s.count}</div>
                    <div className="w-full bg-zinc-800 rounded-t" style={{ height: `${h}%` }} />
                    <div className="text-xs mt-1">Size {s.mapped_size}</div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}
    </AdminShell>
  );
}

function StatCard({ title, value }: { title: string; value: string | number }) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="text-sm text-zinc-500">{title}</div>
        <div className="text-2xl font-bold mt-1">{value}</div>
      </CardContent>
    </Card>
  );
}
