import Database from "better-sqlite3";
import path from "path";

const DB_PATH = path.join(process.cwd(), "data", "admin.db");

let _db: Database.Database | null = null;

export function getDb(): Database.Database {
  if (!_db) {
    const fs = require("fs");
    fs.mkdirSync(path.dirname(DB_PATH), { recursive: true });
    _db = new Database(DB_PATH);
    _db.pragma("journal_mode = WAL");
    _db.pragma("foreign_keys = ON");
    migrate(_db);
  }
  return _db;
}

function migrate(db: Database.Database) {
  db.exec(`
    CREATE TABLE IF NOT EXISTS admins (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL,
      created_at TEXT DEFAULT (datetime('now'))
    );

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
}

export function seedAdmin(email: string, passwordHash: string) {
  const db = getDb();
  const existing = db.prepare("SELECT id FROM admins WHERE email = ?").get(email);
  if (!existing) {
    db.prepare("INSERT INTO admins (email, password_hash) VALUES (?, ?)").run(email, passwordHash);
  }
}
