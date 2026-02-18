"use client";

import { useEffect, useState } from "react";
import { AdminShell } from "@/components/admin-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { toast } from "sonner";

interface Rule {
  id: number;
  finger: string;
  min_width_mm: number;
  max_width_mm: number;
  mapped_size: number;
  priority: number;
}

interface PreviewResult {
  finger: string;
  width_mm: number;
  mapped_size: number | null;
  rule_id: number | null;
}

const FINGERS = ["all", "thumb", "index", "middle", "ring", "pinky"];

export default function RulesPage() {
  const [rules, setRules] = useState<Rule[]>([]);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Rule | null>(null);
  const [previewFinger, setPreviewFinger] = useState("thumb");
  const [previewWidth, setPreviewWidth] = useState("14.0");
  const [previewResult, setPreviewResult] = useState<PreviewResult | null>(null);

  const load = () => fetch("/api/rules").then((r) => r.json()).then(setRules);
  useEffect(() => { load(); }, []);

  async function handleSave(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const data = {
      finger: fd.get("finger"),
      min_width_mm: Number(fd.get("min_width_mm")),
      max_width_mm: Number(fd.get("max_width_mm")),
      mapped_size: Number(fd.get("mapped_size")),
      priority: Number(fd.get("priority") || 0),
    };
    const url = editing ? `/api/rules/${editing.id}` : "/api/rules";
    const method = editing ? "PUT" : "POST";
    const res = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
    if (!res.ok) {
      const err = await res.json();
      toast.error(err.error || "Failed to save");
      return;
    }
    toast.success(editing ? "Rule updated" : "Rule created");
    setDialogOpen(false);
    setEditing(null);
    load();
  }

  async function handleDelete(id: number) {
    if (!confirm("Delete this rule?")) return;
    await fetch(`/api/rules/${id}`, { method: "DELETE" });
    toast.success("Deleted");
    load();
  }

  async function handlePreview() {
    const res = await fetch("/api/rules/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ measurements: [{ finger: previewFinger, width_mm: Number(previewWidth) }] }),
    });
    const data = await res.json();
    setPreviewResult(data.results?.[0] ?? null);
  }

  return (
    <AdminShell>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Size Mapping Rules</h1>
        <Dialog open={dialogOpen} onOpenChange={(o) => { setDialogOpen(o); if (!o) setEditing(null); }}>
          <DialogTrigger asChild>
            <Button onClick={() => setEditing(null)}>+ Add Rule</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader><DialogTitle>{editing ? "Edit Rule" : "Add Rule"}</DialogTitle></DialogHeader>
            <form onSubmit={handleSave} className="space-y-3">
              <div>
                <Label>Finger</Label>
                <Select name="finger" defaultValue={editing?.finger ?? "all"}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {FINGERS.map((f) => <SelectItem key={f} value={f}>{f}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div><Label>Min Width (mm)</Label><Input name="min_width_mm" type="number" step="0.1" defaultValue={editing?.min_width_mm ?? ""} required /></div>
                <div><Label>Max Width (mm)</Label><Input name="max_width_mm" type="number" step="0.1" defaultValue={editing?.max_width_mm ?? ""} required /></div>
              </div>
              <div><Label>Mapped Size</Label><Input name="mapped_size" type="number" min={0} max={9} defaultValue={editing?.mapped_size ?? ""} required /></div>
              <div><Label>Priority</Label><Input name="priority" type="number" defaultValue={editing?.priority ?? 0} /></div>
              <Button type="submit" className="w-full">Save</Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Finger</TableHead>
                <TableHead>Min (mm)</TableHead>
                <TableHead>Max (mm)</TableHead>
                <TableHead>→ Size</TableHead>
                <TableHead>Priority</TableHead>
                <TableHead className="w-24">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rules.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="capitalize">{r.finger}</TableCell>
                  <TableCell>{r.min_width_mm}</TableCell>
                  <TableCell>{r.max_width_mm}</TableCell>
                  <TableCell className="font-mono font-bold">{r.mapped_size}</TableCell>
                  <TableCell>{r.priority}</TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <Button size="sm" variant="ghost" onClick={() => { setEditing(r); setDialogOpen(true); }}>✏️</Button>
                      <Button size="sm" variant="ghost" onClick={() => handleDelete(r.id)}>🗑️</Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
              {rules.length === 0 && (
                <TableRow><TableCell colSpan={6} className="text-center text-zinc-400 py-8">No rules yet.</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </div>

        <div>
          <Card>
            <CardHeader><CardTitle>Preview</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <div>
                <Label>Finger</Label>
                <Select value={previewFinger} onValueChange={setPreviewFinger}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {FINGERS.filter((f) => f !== "all").map((f) => <SelectItem key={f} value={f}>{f}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Width (mm)</Label>
                <Input type="number" step="0.1" value={previewWidth} onChange={(e) => setPreviewWidth(e.target.value)} />
              </div>
              <Button onClick={handlePreview} className="w-full">Test</Button>
              <Separator />
              {previewResult && (
                <div className="text-center py-2">
                  <div className="text-sm text-zinc-500">{previewResult.finger} @ {previewResult.width_mm}mm</div>
                  <div className="text-3xl font-bold mt-1">
                    {previewResult.mapped_size !== null ? `Size ${previewResult.mapped_size}` : "No match"}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </AdminShell>
  );
}
