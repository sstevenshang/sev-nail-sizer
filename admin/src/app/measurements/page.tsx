"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AdminShell } from "@/components/admin-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

interface Measurement {
  id: number;
  session_id: string | null;
  finger: string;
  width_mm: number;
  confidence: number;
  mapped_size: number | null;
  debug_image_url: string | null;
  created_at: string;
}

interface PageData {
  data: Measurement[];
  total: number;
  page: number;
  pages: number;
}

export default function MeasurementsPage() {
  const [pageData, setPageData] = useState<PageData | null>(null);
  const [page, setPage] = useState(1);
  const [finger, setFinger] = useState("all");
  const [minConf, setMinConf] = useState("");

  useEffect(() => {
    const params = new URLSearchParams({ page: String(page), limit: "12" });
    if (finger !== "all") params.set("finger", finger);
    if (minConf) params.set("min_confidence", minConf);
    fetch(`/api/measurements?${params}`).then((r) => r.json()).then(setPageData);
  }, [page, finger, minConf]);

  return (
    <AdminShell>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Measurements</h1>
        <div className="flex gap-2 items-center">
          <Select value={finger} onValueChange={(v) => { setFinger(v); setPage(1); }}>
            <SelectTrigger className="w-32"><SelectValue placeholder="Finger" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All fingers</SelectItem>
              {["thumb", "index", "middle", "ring", "pinky"].map((f) => (
                <SelectItem key={f} value={f}>{f}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input placeholder="Min confidence" type="number" step="0.1" min={0} max={1} className="w-36"
            value={minConf} onChange={(e) => { setMinConf(e.target.value); setPage(1); }} />
        </div>
      </div>

      {pageData && pageData.data.length > 0 ? (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
            {pageData.data.map((m) => (
              <Link key={m.id} href={`/measurements/${m.id}`}>
                <Card className="hover:shadow-md transition-shadow cursor-pointer">
                  <CardContent className="pt-4">
                    {m.debug_image_url && (
                      <div className="w-full h-32 bg-zinc-200 rounded mb-3 flex items-center justify-center text-zinc-400">
                        <img src={m.debug_image_url} alt="debug" className="h-full object-contain" onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }} />
                      </div>
                    )}
                    <div className="flex items-center justify-between">
                      <span className="capitalize font-medium">{m.finger}</span>
                      <Badge variant={m.confidence > 0.8 ? "default" : m.confidence > 0.5 ? "secondary" : "destructive"}>
                        {(m.confidence * 100).toFixed(0)}%
                      </Badge>
                    </div>
                    <div className="text-sm text-zinc-500 mt-1">
                      {m.width_mm}mm → {m.mapped_size !== null ? `Size ${m.mapped_size}` : "Unmapped"}
                    </div>
                    <div className="text-xs text-zinc-400 mt-1">{new Date(m.created_at).toLocaleString()}</div>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>

          <div className="flex items-center justify-between">
            <span className="text-sm text-zinc-500">{pageData.total} total</span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>← Prev</Button>
              <span className="text-sm py-1">Page {page} of {pageData.pages}</span>
              <Button variant="outline" size="sm" disabled={page >= pageData.pages} onClick={() => setPage(page + 1)}>Next →</Button>
            </div>
          </div>
        </>
      ) : (
        <div className="text-center text-zinc-400 py-16">No measurements found.</div>
      )}
    </AdminShell>
  );
}
