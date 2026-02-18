import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/db";

export async function PUT(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const body = await req.json();
  const { finger, min_width_mm, max_width_mm, mapped_size, priority } = body;
  const db = getDb();
  const result = db
    .prepare("UPDATE size_rules SET finger=?, min_width_mm=?, max_width_mm=?, mapped_size=?, priority=? WHERE id=?")
    .run(finger, min_width_mm, max_width_mm, mapped_size, priority ?? 0, id);
  if (result.changes === 0) return NextResponse.json({ error: "Not found" }, { status: 404 });
  return NextResponse.json({ ok: true });
}

export async function DELETE(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const db = getDb();
  const result = db.prepare("DELETE FROM size_rules WHERE id=?").run(id);
  if (result.changes === 0) return NextResponse.json({ error: "Not found" }, { status: 404 });
  return NextResponse.json({ ok: true });
}
