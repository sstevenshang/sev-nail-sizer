import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/db";

export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const page = Math.max(1, Number(url.searchParams.get("page") || 1));
  const limit = Math.min(100, Math.max(1, Number(url.searchParams.get("limit") || 20)));
  const finger = url.searchParams.get("finger");
  const minConfidence = url.searchParams.get("min_confidence");
  const dateFrom = url.searchParams.get("date_from");
  const dateTo = url.searchParams.get("date_to");

  const db = getDb();
  const conditions: string[] = [];
  const params: (string | number)[] = [];

  if (finger) {
    conditions.push("finger = ?");
    params.push(finger);
  }
  if (minConfidence) {
    conditions.push("confidence >= ?");
    params.push(Number(minConfidence));
  }
  if (dateFrom) {
    conditions.push("created_at >= ?");
    params.push(dateFrom);
  }
  if (dateTo) {
    conditions.push("created_at <= ?");
    params.push(dateTo);
  }

  const where = conditions.length > 0 ? "WHERE " + conditions.join(" AND ") : "";
  const offset = (page - 1) * limit;

  const total = (db.prepare(`SELECT COUNT(*) as count FROM measurements ${where}`).get(...params) as { count: number }).count;
  const rows = db.prepare(`SELECT * FROM measurements ${where} ORDER BY created_at DESC LIMIT ? OFFSET ?`).all(...params, limit, offset);

  return NextResponse.json({ data: rows, total, page, limit, pages: Math.ceil(total / limit) });
}
