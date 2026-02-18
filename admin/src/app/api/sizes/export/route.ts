import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import Papa from "papaparse";

export async function GET() {
  const db = getDb();
  const sizes = db.prepare("SELECT size_number, width_mm, length_mm, curvature_mm, label FROM nail_sizes ORDER BY size_number ASC").all();
  const csv = Papa.unparse(sizes as Record<string, unknown>[]);
  return new NextResponse(csv, {
    headers: {
      "Content-Type": "text/csv",
      "Content-Disposition": "attachment; filename=nail_sizes.csv",
    },
  });
}
