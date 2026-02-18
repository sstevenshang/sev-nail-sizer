"use client";

import { useEffect, useState, use } from "react";
import { AdminShell } from "@/components/admin-shell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import Link from "next/link";

interface Measurement {
  id: number;
  session_id: string | null;
  finger: string;
  width_mm: number;
  length_mm: number | null;
  curvature_mm: number | null;
  confidence: number;
  mapped_size: number | null;
  debug_image_url: string | null;
  warnings: string | null;
  created_at: string;
}

export default function MeasurementDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [m, setM] = useState<Measurement | null>(null);

  useEffect(() => {
    fetch(`/api/measurements/${id}`).then((r) => r.json()).then(setM);
  }, [id]);

  if (!m) return <AdminShell><div className="text-center py-16">Loading...</div></AdminShell>;

  return (
    <AdminShell>
      <div className="mb-4">
        <Link href="/measurements"><Button variant="ghost">← Back</Button></Link>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader><CardTitle>Measurement #{m.id}</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <Row label="Finger" value={<span className="capitalize">{m.finger}</span>} />
            <Row label="Width" value={`${m.width_mm} mm`} />
            <Row label="Length" value={m.length_mm ? `${m.length_mm} mm` : "—"} />
            <Row label="Curvature" value={m.curvature_mm ? `${m.curvature_mm} mm` : "—"} />
            <Row label="Confidence" value={
              <Badge variant={m.confidence > 0.8 ? "default" : m.confidence > 0.5 ? "secondary" : "destructive"}>
                {(m.confidence * 100).toFixed(1)}%
              </Badge>
            } />
            <Row label="Mapped Size" value={m.mapped_size !== null ? `Size ${m.mapped_size}` : "Unmapped"} />
            <Row label="Session" value={m.session_id ?? "—"} />
            <Row label="Date" value={new Date(m.created_at).toLocaleString()} />
            {m.warnings && <Row label="Warnings" value={<span className="text-amber-600">{m.warnings}</span>} />}
          </CardContent>
        </Card>

        {m.debug_image_url && (
          <Card>
            <CardHeader><CardTitle>Debug Image</CardTitle></CardHeader>
            <CardContent>
              <img src={m.debug_image_url} alt="Debug" className="w-full rounded" />
            </CardContent>
          </Card>
        )}
      </div>
    </AdminShell>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between items-center">
      <span className="text-sm text-zinc-500">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}
