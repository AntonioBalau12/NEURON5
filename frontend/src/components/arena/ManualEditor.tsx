'use client';

import { useRef, useState } from 'react';
import type { ClipboardEvent } from 'react';
import { Plus, Save, Trash2 } from 'lucide-react';
import { datasetsApi, type Dataset } from '@/lib/api';
import { Button, ErrorNotice } from './ui';

const COLUMNS = ['id', 'text', 'date'] as const;
type ColumnKey = (typeof COLUMNS)[number];

interface DraftRow {
  key: string;
  id: string;
  text: string;
  date: string;
}

let rowCounter = 0;

function makeRow(): DraftRow {
  rowCounter += 1;
  return { key: 'row-' + rowCounter, id: '', text: '', date: '' };
}

export interface ManualEditorProps {
  dataset: Dataset | null;
  active: boolean;
  sessionReady: boolean;
  onSaved: (dataset: Dataset) => void;
}

export default function ManualEditor({ active, sessionReady, onSaved }: ManualEditorProps) {
  const [rows, setRows] = useState<DraftRow[]>(() => [makeRow()]);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<unknown>(null);
  const focusedRef = useRef<{ rowKey: string; col: number } | null>(null);

  function updateCell(rowKey: string, field: ColumnKey, value: string) {
    setRows((previous) =>
      previous.map((row) => (row.key === rowKey ? { ...row, [field]: value } : row)),
    );
  }

  function addRow() {
    setRows((previous) => [...previous, makeRow()]);
  }

  function deleteRow(rowKey: string) {
    setRows((previous) => previous.filter((row) => row.key !== rowKey));
  }

  function handlePaste(event: ClipboardEvent<HTMLDivElement>) {
    const target = event.target as HTMLElement | null;
    if (!(target instanceof HTMLInputElement)) return;
    const text = event.clipboardData.getData('text/plain');
    if (!text) return;
    const normalized = text.replace(/\r\n?/g, '\n');
    const lines = normalized.split('\n');
    if (lines.length > 1 && lines[lines.length - 1] === '') lines.pop();
    const matrix = lines.map((line) => line.split('\t'));
    if (!(matrix.length > 1 || matrix.some((cells) => cells.length > 1))) return;

    event.preventDefault();
    const focus = focusedRef.current;
    let startIndex = focus ? rows.findIndex((row) => row.key === focus.rowKey) : 0;
    if (startIndex < 0) startIndex = Math.max(0, rows.length - 1);
    const startColumn = focus?.col ?? 0;

    const next = rows.map((row) => ({ ...row }));
    while (next.length < startIndex + matrix.length) next.push(makeRow());
    matrix.forEach((cells, rowOffset) => {
      const targetRow = next[startIndex + rowOffset];
      if (!targetRow) return;
      cells.forEach((cell, columnOffset) => {
        const columnIndex = startColumn + columnOffset;
        if (columnIndex >= COLUMNS.length) return;
        targetRow[COLUMNS[columnIndex]] = cell;
      });
    });
    setRows(next);
  }

  async function handleSave() {
    if (saving || !sessionReady) return;
    setSaving(true);
    setSaveError(null);
    try {
      const snapshot = rows.map((row) => [row.id, row.text, row.date]);
      const saved = await datasetsApi.createManual({ columns: [...COLUMNS], rows: snapshot });
      // Manual drafts always use the same three columns: confirm the mapping
      // automatically so the user only has to press Process.
      const ready = await datasetsApi.updateMapping(saved.id, {
        textColumn: 'text',
        dateColumn: 'date',
        idColumn: 'id',
        resultColumn: 'label',
      });
      onSaved(ready);
    } catch (error) {
      setSaveError(error);
    } finally {
      setSaving(false);
    }
  }

  const visibleColumns: ColumnKey[] = ['text', 'date', 'id'];

  return (
    <div>
      <div className="flex items-center justify-between gap-2">
        <Button size="sm" onClick={addRow} title="Add a row">
          <Plus className="h-3.5 w-3.5" aria-hidden="true" /> Add row
        </Button>
        <Button
          size="sm"
          variant="primary"
          onClick={handleSave}
          loading={saving}
          disabled={!sessionReady}
          title={sessionReady ? 'Save the draft' : 'Waiting for the session'}
        >
          <Save className="h-3.5 w-3.5" aria-hidden="true" /> Save
        </Button>
      </div>

      <div
        onPaste={handlePaste}
        className="mt-3 overflow-hidden rounded-xl border border-black/[0.08]"
      >
        <div className="overflow-x-auto" data-active={active ? 'true' : 'false'}>
          <table className="w-full min-w-[560px] border-collapse text-left text-xs">
            <thead className="bg-[#f7f7f7] text-[10px] uppercase tracking-wider text-black/50">
              <tr>
                <th scope="col" className="border-b border-black/[0.08] px-3 py-2 font-semibold">
                  Text <span className="text-red-500">*</span>
                </th>
                <th scope="col" className="w-36 border-b border-black/[0.08] px-3 py-2 font-semibold">
                  Date
                </th>
                <th scope="col" className="w-32 border-b border-black/[0.08] px-3 py-2 font-semibold">
                  Id
                </th>
                <th scope="col" className="w-10 border-b border-black/[0.08] px-2 py-2">
                  <span className="sr-only">Delete</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-black/[0.06]">
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-[11px] text-black/45">
                    No rows. Add a row to start.
                  </td>
                </tr>
              ) : null}
              {rows.map((row, rowIndex) => (
                <tr key={row.key} className="align-top">
                  <td className="px-1.5 py-1">
                    <input
                      value={row.text}
                      onChange={(event) => updateCell(row.key, 'text', event.target.value)}
                      onFocus={() => {
                        focusedRef.current = { rowKey: row.key, col: 0 };
                      }}
                      aria-label={'Row ' + (rowIndex + 1) + ' sentence'}
                      placeholder="One sentence"
                      spellCheck={false}
                      autoComplete="off"
                      className="w-full rounded-md border border-transparent bg-transparent px-2 py-1.5 text-[#202020] outline-none transition placeholder:text-black/25 focus:border-[#9ebc19]/40 focus:bg-white focus:ring-2 focus:ring-[#9ebc19]/15"
                    />
                  </td>
                  <td className="px-1.5 py-1">
                    <input
                      value={row.date}
                      onChange={(event) => updateCell(row.key, 'date', event.target.value)}
                      onFocus={() => {
                        focusedRef.current = { rowKey: row.key, col: 2 };
                      }}
                      aria-label={'Row ' + (rowIndex + 1) + ' date'}
                      placeholder="yyyy-mm-dd"
                      spellCheck={false}
                      autoComplete="off"
                      className="w-full rounded-md border border-transparent bg-transparent px-2 py-1.5 font-mono text-[11px] text-[#202020] outline-none transition placeholder:text-black/25 focus:border-[#9ebc19]/40 focus:bg-white focus:ring-2 focus:ring-[#9ebc19]/15"
                    />
                  </td>
                  <td className="px-1.5 py-1">
                    <input
                      value={row.id}
                      onChange={(event) => updateCell(row.key, 'id', event.target.value)}
                      onFocus={() => {
                        focusedRef.current = { rowKey: row.key, col: 1 };
                      }}
                      aria-label={'Row ' + (rowIndex + 1) + ' id'}
                      placeholder="optional"
                      spellCheck={false}
                      autoComplete="off"
                      className="w-full rounded-md border border-transparent bg-transparent px-2 py-1.5 font-mono text-[11px] text-[#202020] outline-none transition placeholder:text-black/25 focus:border-[#9ebc19]/40 focus:bg-white focus:ring-2 focus:ring-[#9ebc19]/15"
                    />
                  </td>
                  <td className="px-2 py-2 text-center">
                    <button
                      type="button"
                      onClick={() => deleteRow(row.key)}
                      aria-label={'Delete row ' + (rowIndex + 1)}
                      title="Delete row"
                      className="rounded-md p-1.5 text-black/35 transition-colors hover:bg-red-50 hover:text-red-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#9ebc19]/40"
                    >
                      <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {saveError ? (
        <ErrorNotice
          className="mt-3"
          error={saveError}
          onRetry={handleSave}
          retryLabel="Try again"
          retryDisabled={saving || !sessionReady}
          onDismiss={() => setSaveError(null)}
        />
      ) : null}
    </div>
  );
}
