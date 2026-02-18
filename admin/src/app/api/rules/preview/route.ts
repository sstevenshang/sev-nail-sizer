import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/db";

interface MeasurementInput {
  finger: string;
  width_mm: number;
}

interface RuleRow {
  id: number;
  finger: string;
  min_width_mm: number;
  max_width_mm: number;
  mapped_size: number;
  priority: number;
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  const measurements: MeasurementInput[] = body.measurements;
  if (!measurements || !Array.isArray(measurements)) {
    return NextResponse.json({ error: "measurements array required" }, { status: 400 });
  }

  const db = getDb();
  const rules = db.prepare("SELECT * FROM size_rules ORDER BY priority DESC").all() as RuleRow[];

  const results = measurements.map((m) => {
    // Find matching rule: first check finger-specific, then "all"
    const match = rules.find(
      (r) =>
        (r.finger === m.finger || r.finger === "all") &&
        m.width_mm >= r.min_width_mm &&
        m.width_mm < r.max_width_mm
    );
    return {
      finger: m.finger,
      width_mm: m.width_mm,
      mapped_size: match ? match.mapped_size : null,
      rule_id: match ? match.id : null,
    };
  });

  return NextResponse.json({ results });
}
