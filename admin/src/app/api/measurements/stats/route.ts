import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";

export async function GET() {
  const db = getDb();
  const total = (db.prepare("SELECT COUNT(*) as count FROM measurements").get() as { count: number }).count;
  const avgConfidence = (db.prepare("SELECT AVG(confidence) as avg FROM measurements").get() as { avg: number | null }).avg;
  const byFinger = db.prepare("SELECT finger, COUNT(*) as count, AVG(confidence) as avg_confidence FROM measurements GROUP BY finger").all();
  const recent = db.prepare("SELECT COUNT(*) as count FROM measurements WHERE created_at >= datetime('now', '-7 days')").get() as { count: number };
  const sizeDist = db.prepare("SELECT mapped_size, COUNT(*) as count FROM measurements WHERE mapped_size IS NOT NULL GROUP BY mapped_size ORDER BY mapped_size").all();

  return NextResponse.json({
    total_measurements: total,
    avg_confidence: avgConfidence ? Math.round(avgConfidence * 100) / 100 : null,
    last_7_days: recent.count,
    by_finger: byFinger,
    size_distribution: sizeDist,
  });
}
