import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/db";

export async function GET() {
  const db = getDb();
  const sets = db.prepare("SELECT * FROM size_sets ORDER BY name ASC").all();
  return NextResponse.json(sets);
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  const { name, thumb_size, index_size, middle_size, ring_size, pinky_size, shopify_variant_id } = body;
  if (!name) {
    return NextResponse.json({ error: "name required" }, { status: 400 });
  }
  const db = getDb();
  const result = db
    .prepare(
      "INSERT INTO size_sets (name, thumb_size, index_size, middle_size, ring_size, pinky_size, shopify_variant_id) VALUES (?, ?, ?, ?, ?, ?, ?)"
    )
    .run(name, thumb_size ?? null, index_size ?? null, middle_size ?? null, ring_size ?? null, pinky_size ?? null, shopify_variant_id ?? null);
  return NextResponse.json({ id: result.lastInsertRowid }, { status: 201 });
}
