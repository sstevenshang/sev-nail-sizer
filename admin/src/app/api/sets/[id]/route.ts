import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/db";

export async function PUT(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const body = await req.json();
  const { name, thumb_size, index_size, middle_size, ring_size, pinky_size, shopify_variant_id } = body;
  const db = getDb();
  const result = db
    .prepare(
      "UPDATE size_sets SET name=?, thumb_size=?, index_size=?, middle_size=?, ring_size=?, pinky_size=?, shopify_variant_id=? WHERE id=?"
    )
    .run(name, thumb_size ?? null, index_size ?? null, middle_size ?? null, ring_size ?? null, pinky_size ?? null, shopify_variant_id ?? null, id);
  if (result.changes === 0) return NextResponse.json({ error: "Not found" }, { status: 404 });
  return NextResponse.json({ ok: true });
}

export async function DELETE(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const db = getDb();
  const result = db.prepare("DELETE FROM size_sets WHERE id=?").run(id);
  if (result.changes === 0) return NextResponse.json({ error: "Not found" }, { status: 404 });
  return NextResponse.json({ ok: true });
}
