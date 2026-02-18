"use client";

import { useEffect, useState, useRef } from "react";
import { AdminShell } from "@/components/admin-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";

interface NailSize {
  id: number;
  size_number: number;
  width_mm: number;
  length_mm: number | null;
  curvature_mm: number | null;
  label: string | null;
}

export default function SizesPage() {
  const [sizes, setSizes] = useState<NailSize[]>([]);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<NailSize | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = () => fetch("/api/sizes").then((r) => r.json()).then(setSizes);
  useEffect(() => { load(); }, []);

  async function handleSave(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const data = {
      size_number: Number(fd.get("size_number")),
      width_mm: Number(fd.get("width_mm")),
      length_mm: fd.get("length_mm") ? Number(fd.get("length_mm")) : null,
      curvature_mm: fd.get("curvature_mm") ? Number(fd.get("curvature_mm")) : null,
      label: fd.get("label") || null,
    };
    const url = editing ? `/api/sizes/${editing.id}` : "/api/sizes";
    const method = editing ? "PUT" : "POST";
    const res = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
    if (!res.ok) {
      const err = await res.json();
      toast.error(err.error || "Failed to save");
      return;
    }
    toast.success(editing ? "Size updated" : "Size created");
    setDialogOpen(false);
    setEditing(null);
    load();
  }

  async function handleDelete(id: number) {
    if (!confirm("Delete this size?")) return;
    await fetch(`/api/sizes/${id}`, { method: "DELETE" });
    toast.success("Deleted");
    load();
  }

  async function handleExport() {
    const res = await fetch("/api/sizes/export");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "nail_sizes.csv";
    a.click();
  }

  async function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    const res = await fetch("/api/sizes/import", { method: "POST", body: text });
    const data = await res.json();
    toast.success(`Imported ${data.imported} sizes`);
    load();
    if (fileRef.current) fileRef.current.value = "";
  }

  return (
    <AdminShell>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Size Chart</h1>
        <div className="flex gap-2">
          <Button variant="outline" onClick={handleExport}>Export CSV</Button>
          <Button variant="outline" onClick={() => fileRef.current?.click()}>Import CSV</Button>
          <input ref={fileRef} type="file" accept=".csv" className="hidden" onChange={handleImport} />
          <Dialog open={dialogOpen} onOpenChange={(o) => { setDialogOpen(o); if (!o) setEditing(null); }}>
            <DialogTrigger asChild>
              <Button onClick={() => setEditing(null)}>+ Add Size</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>{editing ? "Edit Size" : "Add Size"}</DialogTitle></DialogHeader>
              <form onSubmit={handleSave} className="space-y-3">
                <div><Label>Size Number</Label><Input name="size_number" type="number" min={0} max={9} defaultValue={editing?.size_number ?? ""} required /></div>
                <div><Label>Width (mm)</Label><Input name="width_mm" type="number" step="0.1" defaultValue={editing?.width_mm ?? ""} required /></div>
                <div><Label>Length (mm)</Label><Input name="length_mm" type="number" step="0.1" defaultValue={editing?.length_mm ?? ""} /></div>
                <div><Label>Curvature (mm)</Label><Input name="curvature_mm" type="number" step="0.1" defaultValue={editing?.curvature_mm ?? ""} /></div>
                <div><Label>Label</Label><Input name="label" defaultValue={editing?.label ?? ""} /></div>
                <Button type="submit" className="w-full">Save</Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Size</TableHead>
            <TableHead>Width (mm)</TableHead>
            <TableHead>Length (mm)</TableHead>
            <TableHead>Curvature (mm)</TableHead>
            <TableHead>Label</TableHead>
            <TableHead className="w-24">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sizes.map((s) => (
            <TableRow key={s.id}>
              <TableCell className="font-mono">{s.size_number}</TableCell>
              <TableCell>{s.width_mm}</TableCell>
              <TableCell>{s.length_mm ?? "—"}</TableCell>
              <TableCell>{s.curvature_mm ?? "—"}</TableCell>
              <TableCell>{s.label ?? "—"}</TableCell>
              <TableCell>
                <div className="flex gap-1">
                  <Button size="sm" variant="ghost" onClick={() => { setEditing(s); setDialogOpen(true); }}>✏️</Button>
                  <Button size="sm" variant="ghost" onClick={() => handleDelete(s.id)}>🗑️</Button>
                </div>
              </TableCell>
            </TableRow>
          ))}
          {sizes.length === 0 && (
            <TableRow><TableCell colSpan={6} className="text-center text-zinc-400 py-8">No sizes yet. Add one or import a CSV.</TableCell></TableRow>
          )}
        </TableBody>
      </Table>
    </AdminShell>
  );
}
