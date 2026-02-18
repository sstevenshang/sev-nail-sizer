import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import Papa from "papaparse";

export async function POST(req: NextRequest) {
  const text = await req.text();
  const parsed = Papa.parse(text, { header: true, skipEmptyLines: true });
  if (parsed.errors.length > 0) {
    return NextResponse.json({ error: "CSV parse error", details: parsed.errors }, { status: 400 });
  }
  const db = getDb();
  const stmt = db.prepare(
    `INSERT OR REPLACE INTO nail_sizes (size_number, width_mm, length_mm, curvature_mm, label, updated_at)
     VALUES (?, ?, ?, ?, ?, datetime('now'))`
  );
  let count = 0;
  const txn = db.transaction(() => {
    for (const row of parsed.data as Record<string, string>[]) {
      if (!row.size_number || !row.width_mm) continue;
      stmt.run(
        Number(row.size_number),
        Number(row.width_mm),
        row.length_mm ? Number(row.length_mm) : null,
        row.curvature_mm ? Number(row.curvature_mm) : null,
        row.label || null
      );
      count++;
    }
  });
  txn();
  return NextResponse.json({ imported: count });
}
