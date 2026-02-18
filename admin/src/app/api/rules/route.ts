import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/db";

export async function GET() {
  const db = getDb();
  const rules = db.prepare("SELECT * FROM size_rules ORDER BY finger, min_width_mm ASC").all();
  return NextResponse.json(rules);
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  const { finger, min_width_mm, max_width_mm, mapped_size, priority } = body;
  if (!finger || min_width_mm == null || max_width_mm == null || mapped_size == null) {
    return NextResponse.json({ error: "finger, min_width_mm, max_width_mm, mapped_size required" }, { status: 400 });
  }
  const db = getDb();
  const result = db
    .prepare("INSERT INTO size_rules (finger, min_width_mm, max_width_mm, mapped_size, priority) VALUES (?, ?, ?, ?, ?)")
    .run(finger, min_width_mm, max_width_mm, mapped_size, priority ?? 0);
  return NextResponse.json({ id: result.lastInsertRowid }, { status: 201 });
}
