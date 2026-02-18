import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/db";

export async function GET() {
  const db = getDb();
  const sizes = db.prepare("SELECT * FROM nail_sizes ORDER BY size_number ASC").all();
  return NextResponse.json(sizes);
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  const { size_number, width_mm, length_mm, curvature_mm, label } = body;
  if (size_number == null || width_mm == null) {
    return NextResponse.json({ error: "size_number and width_mm required" }, { status: 400 });
  }
  const db = getDb();
  try {
    const result = db
      .prepare(
        "INSERT INTO nail_sizes (size_number, width_mm, length_mm, curvature_mm, label) VALUES (?, ?, ?, ?, ?)"
      )
      .run(size_number, width_mm, length_mm ?? null, curvature_mm ?? null, label ?? null);
    return NextResponse.json({ id: result.lastInsertRowid }, { status: 201 });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "Unknown error";
    if (msg.includes("UNIQUE")) {
      return NextResponse.json({ error: "Size number already exists" }, { status: 409 });
    }
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
