"use client";

import { useEffect, useState } from "react";
import { AdminShell } from "@/components/admin-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";

interface SizeSet {
  id: number;
  name: string;
  thumb_size: number | null;
  index_size: number | null;
  middle_size: number | null;
  ring_size: number | null;
  pinky_size: number | null;
  shopify_variant_id: string | null;
}

const FINGER_FIELDS = ["thumb_size", "index_size", "middle_size", "ring_size", "pinky_size"] as const;
const FINGER_LABELS = ["Thumb", "Index", "Middle", "Ring", "Pinky"];

export default function SetsPage() {
  const [sets, setSets] = useState<SizeSet[]>([]);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<SizeSet | null>(null);

  const load = () => fetch("/api/sets").then((r) => r.json()).then(setSets);
  useEffect(() => { load(); }, []);

  async function handleSave(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const data: Record<string, unknown> = { name: fd.get("name"), shopify_variant_id: fd.get("shopify_variant_id") || null };
    FINGER_FIELDS.forEach((f) => { const v = fd.get(f); data[f] = v ? Number(v) : null; });
    const url = editing ? `/api/sets/${editing.id}` : "/api/sets";
    const method = editing ? "PUT" : "POST";
    const res = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
    if (!res.ok) { toast.error("Failed to save"); return; }
    toast.success(editing ? "Set updated" : "Set created");
    setDialogOpen(false);
    setEditing(null);
    load();
  }

  async function handleDelete(id: number) {
    if (!confirm("Delete this set?")) return;
    await fetch(`/api/sets/${id}`, { method: "DELETE" });
    toast.success("Deleted");
    load();
  }

  return (
    <AdminShell>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Pre-packaged Sets</h1>
        <Dialog open={dialogOpen} onOpenChange={(o) => { setDialogOpen(o); if (!o) setEditing(null); }}>
          <DialogTrigger asChild>
            <Button onClick={() => setEditing(null)}>+ Add Set</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader><DialogTitle>{editing ? "Edit Set" : "Add Set"}</DialogTitle></DialogHeader>
            <form onSubmit={handleSave} className="space-y-3">
              <div><Label>Name</Label><Input name="name" defaultValue={editing?.name ?? ""} required /></div>
              <div className="grid grid-cols-5 gap-2">
                {FINGER_FIELDS.map((f, i) => (
                  <div key={f}><Label className="text-xs">{FINGER_LABELS[i]}</Label><Input name={f} type="number" min={0} max={9} defaultValue={editing?.[f] ?? ""} /></div>
                ))}
              </div>
              <div><Label>Shopify Variant ID</Label><Input name="shopify_variant_id" defaultValue={editing?.shopify_variant_id ?? ""} /></div>
              <Button type="submit" className="w-full">Save</Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Thumb</TableHead>
            <TableHead>Index</TableHead>
            <TableHead>Middle</TableHead>
            <TableHead>Ring</TableHead>
            <TableHead>Pinky</TableHead>
            <TableHead>Shopify</TableHead>
            <TableHead className="w-24">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sets.map((s) => (
            <TableRow key={s.id}>
              <TableCell className="font-medium">{s.name}</TableCell>
              {FINGER_FIELDS.map((f) => <TableCell key={f} className="font-mono">{s[f] ?? "—"}</TableCell>)}
              <TableCell className="text-xs text-zinc-400 truncate max-w-[100px]">{s.shopify_variant_id ?? "—"}</TableCell>
              <TableCell>
                <div className="flex gap-1">
                  <Button size="sm" variant="ghost" onClick={() => { setEditing(s); setDialogOpen(true); }}>✏️</Button>
                  <Button size="sm" variant="ghost" onClick={() => handleDelete(s.id)}>🗑️</Button>
                </div>
              </TableCell>
            </TableRow>
          ))}
          {sets.length === 0 && (
            <TableRow><TableCell colSpan={8} className="text-center text-zinc-400 py-8">No sets yet.</TableCell></TableRow>
          )}
        </TableBody>
      </Table>
    </AdminShell>
  );
}
