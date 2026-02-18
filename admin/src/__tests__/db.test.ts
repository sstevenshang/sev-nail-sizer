import { describe, it, expect, beforeAll } from "vitest";
import Database from "better-sqlite3";
import path from "path";
import fs from "fs";

// Use in-memory-like temp DB for tests
const TEST_DB_PATH = path.join(__dirname, "../../data/test.db");

function getTestDb() {
  fs.mkdirSync(path.dirname(TEST_DB_PATH), { recursive: true });
  if (fs.existsSync(TEST_DB_PATH)) fs.unlinkSync(TEST_DB_PATH);
  const db = new Database(TEST_DB_PATH);
  db.pragma("journal_mode = WAL");
  db.exec(`
    CREATE TABLE IF NOT EXISTS nail_sizes (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      size_number INTEGER NOT NULL UNIQUE,
      width_mm REAL NOT NULL,
      length_mm REAL,
      curvature_mm REAL,
      label TEXT,
      created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS size_rules (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      finger TEXT NOT NULL,
      min_width_mm REAL NOT NULL,
      max_width_mm REAL NOT NULL,
      mapped_size INTEGER NOT NULL,
      priority INTEGER DEFAULT 0,
      created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS size_sets (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      thumb_size INTEGER,
      index_size INTEGER,
      middle_size INTEGER,
      ring_size INTEGER,
      pinky_size INTEGER,
      shopify_variant_id TEXT,
      created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS measurements (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      session_id TEXT,
      finger TEXT,
      width_mm REAL,
      length_mm REAL,
      curvature_mm REAL,
      confidence REAL,
      mapped_size INTEGER,
      debug_image_url TEXT,
      warnings TEXT,
      created_at TEXT DEFAULT (datetime('now'))
    );
  `);
  return db;
}

describe("Database operations", () => {
  let db: Database.Database;

  beforeAll(() => {
    db = getTestDb();
  });

  it("should insert and retrieve nail sizes", () => {
    db.prepare("INSERT INTO nail_sizes (size_number, width_mm, length_mm, label) VALUES (?, ?, ?, ?)").run(0, 17.5, 14.0, "Extra Large");
    db.prepare("INSERT INTO nail_sizes (size_number, width_mm, length_mm, label) VALUES (?, ?, ?, ?)").run(5, 13.5, 11.0, "Medium");

    const sizes = db.prepare("SELECT * FROM nail_sizes ORDER BY size_number").all() as { size_number: number; width_mm: number; label: string }[];
    expect(sizes).toHaveLength(2);
    expect(sizes[0].size_number).toBe(0);
    expect(sizes[0].width_mm).toBe(17.5);
    expect(sizes[1].label).toBe("Medium");
  });

  it("should enforce unique size_number", () => {
    expect(() => {
      db.prepare("INSERT INTO nail_sizes (size_number, width_mm) VALUES (?, ?)").run(0, 18.0);
    }).toThrow(/UNIQUE/);
  });

  it("should insert and query size rules", () => {
    db.prepare("INSERT INTO size_rules (finger, min_width_mm, max_width_mm, mapped_size, priority) VALUES (?, ?, ?, ?, ?)").run("all", 10.0, 12.0, 9, 0);
    db.prepare("INSERT INTO size_rules (finger, min_width_mm, max_width_mm, mapped_size, priority) VALUES (?, ?, ?, ?, ?)").run("thumb", 15.0, 18.0, 1, 1);

    const rules = db.prepare("SELECT * FROM size_rules ORDER BY priority DESC").all() as { finger: string; mapped_size: number }[];
    expect(rules).toHaveLength(2);
    expect(rules[0].finger).toBe("thumb");
  });

  it("should match measurement to rule", () => {
    const width = 16.5;
    const finger = "thumb";
    const rules = db.prepare("SELECT * FROM size_rules ORDER BY priority DESC").all() as {
      finger: string; min_width_mm: number; max_width_mm: number; mapped_size: number;
    }[];
    const match = rules.find(
      (r) => (r.finger === finger || r.finger === "all") && width >= r.min_width_mm && width < r.max_width_mm
    );
    expect(match).toBeDefined();
    expect(match!.mapped_size).toBe(1);
  });

  it("should CRUD size sets", () => {
    const res = db.prepare("INSERT INTO size_sets (name, thumb_size, index_size, middle_size, ring_size, pinky_size) VALUES (?, ?, ?, ?, ?, ?)").run("Medium Set", 3, 5, 4, 6, 8);
    expect(res.lastInsertRowid).toBeGreaterThan(0);

    db.prepare("UPDATE size_sets SET shopify_variant_id = ? WHERE id = ?").run("gid://shopify/123", res.lastInsertRowid);

    const set = db.prepare("SELECT * FROM size_sets WHERE id = ?").get(res.lastInsertRowid) as { name: string; shopify_variant_id: string };
    expect(set.name).toBe("Medium Set");
    expect(set.shopify_variant_id).toBe("gid://shopify/123");
  });

  it("should handle measurements with pagination", () => {
    for (let i = 0; i < 25; i++) {
      db.prepare("INSERT INTO measurements (finger, width_mm, confidence, mapped_size) VALUES (?, ?, ?, ?)").run(
        ["thumb", "index", "middle", "ring", "pinky"][i % 5], 10 + Math.random() * 8, 0.5 + Math.random() * 0.5, i % 10
      );
    }

    const total = (db.prepare("SELECT COUNT(*) as count FROM measurements").get() as { count: number }).count;
    expect(total).toBe(25);

    const page1 = db.prepare("SELECT * FROM measurements ORDER BY created_at DESC LIMIT 10 OFFSET 0").all();
    expect(page1).toHaveLength(10);

    const page3 = db.prepare("SELECT * FROM measurements ORDER BY created_at DESC LIMIT 10 OFFSET 20").all();
    expect(page3).toHaveLength(5);
  });
});
