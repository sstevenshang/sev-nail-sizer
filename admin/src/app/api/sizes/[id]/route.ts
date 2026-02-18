import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/db";

export async function PUT(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const body = await req.json();
  const { size_number, width_mm, length_mm, curvature_mm, label } = body;
  const db = getDb();
  const result = db
    .prepare(
      `UPDATE nail_sizes SET size_number=?, width_mm=?, length_mm=?, curvature_mm=?, label=?, updated_at=datetime('now') WHERE id=?`
    )
    .run(size_number, width_mm, length_mm ?? null, curvature_mm ?? null, label ?? null, id);
  if (result.changes === 0) return NextResponse.json({ error: "Not found" }, { status: 404 });
  return NextResponse.json({ ok: true });
}

export async function DELETE(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const db = getDb();
  const result = db.prepare("DELETE FROM nail_sizes WHERE id=?").run(id);
  if (result.changes === 0) return NextResponse.json({ error: "Not found" }, { status: 404 });
  return NextResponse.json({ ok: true });
}
