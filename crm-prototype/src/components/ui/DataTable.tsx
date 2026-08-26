import { useMemo, useRef, useState, type ReactNode } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ArrowUp, ArrowDown } from "lucide-react";
import clsx from "clsx";

export interface Column<T> {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  sortValue?: (row: T) => number | string;
  width?: number | string;
  align?: "right" | "center";
  className?: string;
}

interface Props<T> {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  dense?: boolean;
  virtualize?: boolean;
  maxHeight?: number;
  selectable?: boolean;
  selected?: Set<string>;
  onToggle?: (id: string) => void;
  onToggleAll?: (ids: string[]) => void;
  emptyMessage?: string;
}

export function DataTable<T>({
  rows,
  columns,
  rowKey,
  onRowClick,
  dense,
  virtualize,
  maxHeight = 560,
  selectable,
  selected,
  onToggle,
  onToggleAll,
  emptyMessage = "No records.",
}: Props<T>) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  const sorted = useMemo(() => {
    if (!sortKey) return rows;
    const col = columns.find((c) => c.key === sortKey);
    if (!col?.sortValue) return rows;
    const copy = [...rows];
    copy.sort((a, b) => {
      const av = col.sortValue!(a);
      const bv = col.sortValue!(b);
      if (av < bv) return sortDir === "asc" ? -1 : 1;
      if (av > bv) return sortDir === "asc" ? 1 : -1;
      return 0;
    });
    return copy;
  }, [rows, sortKey, sortDir, columns]);

  const toggleSort = (key: string) => {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const parentRef = useRef<HTMLDivElement>(null);
  const rowH = dense ? 38 : 46;
  const virt = useVirtualizer({
    count: sorted.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => rowH,
    overscan: 12,
  });

  const allIds = sorted.map(rowKey);
  const allSelected = selectable && selected && allIds.length > 0 && allIds.every((id) => selected.has(id));

  const headerRow = (
    <tr>
      {selectable && (
        <th style={{ width: 38 }}>
          <input
            type="checkbox"
            checked={!!allSelected}
            onChange={() => onToggleAll?.(allIds)}
          />
        </th>
      )}
      {columns.map((c) => (
        <th
          key={c.key}
          className={clsx(c.sortValue && "sortable", c.className)}
          style={{ width: c.width, textAlign: c.align }}
          onClick={() => c.sortValue && toggleSort(c.key)}
        >
          <span className="row gap-1" style={{ justifyContent: c.align === "right" ? "flex-end" : undefined }}>
            {c.header}
            {sortKey === c.key && (sortDir === "asc" ? <ArrowUp size={12} /> : <ArrowDown size={12} />)}
          </span>
        </th>
      ))}
    </tr>
  );

  const renderCells = (row: T) => (
    <>
      {selectable && (
        <td style={{ width: 38 }} onClick={(e) => e.stopPropagation()}>
          <input type="checkbox" checked={!!selected?.has(rowKey(row))} onChange={() => onToggle?.(rowKey(row))} />
        </td>
      )}
      {columns.map((c) => (
        <td key={c.key} className={clsx(c.align === "right" && "tnum", c.className)} style={{ textAlign: c.align }}>
          {c.render(row)}
        </td>
      ))}
    </>
  );

  if (rows.length === 0) {
    return <div className="empty">{emptyMessage}</div>;
  }

  if (virtualize) {
    // Virtualize with top/bottom spacer rows in normal table flow. This avoids
    // absolutely-positioned rows, which break in Safari/Firefox because a
    // position:relative <tbody> is not a reliable containing block.
    const items = virt.getVirtualItems();
    const totalSize = virt.getTotalSize();
    const colCount = columns.length + (selectable ? 1 : 0);
    const paddingTop = items.length > 0 ? items[0].start : 0;
    const paddingBottom = items.length > 0 ? totalSize - items[items.length - 1].end : 0;
    return (
      <div className="tbl-wrap" ref={parentRef} style={{ maxHeight, overflow: "auto" }}>
        <table className={clsx("tbl tbl-virt", dense && "dense")}>
          <thead>{headerRow}</thead>
          <tbody>
            {paddingTop > 0 && (
              <tr aria-hidden style={{ height: paddingTop }}>
                <td colSpan={colCount} style={{ padding: 0, border: 0 }} />
              </tr>
            )}
            {items.map((vi) => {
              const row = sorted[vi.index];
              const id = rowKey(row);
              return (
                <tr
                  key={id}
                  data-index={vi.index}
                  className={clsx(selected?.has(id) && "is-selected")}
                  onClick={() => onRowClick?.(row)}
                  style={{ height: rowH, cursor: onRowClick ? "pointer" : undefined }}
                >
                  {renderCells(row)}
                </tr>
              );
            })}
            {paddingBottom > 0 && (
              <tr aria-hidden style={{ height: paddingBottom }}>
                <td colSpan={colCount} style={{ padding: 0, border: 0 }} />
              </tr>
            )}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="tbl-wrap" style={{ maxHeight, overflow: "auto" }}>
      <table className={clsx("tbl", dense && "dense")}>
        <thead>{headerRow}</thead>
        <tbody>
          {sorted.map((row) => {
            const id = rowKey(row);
            return (
              <tr
                key={id}
                className={clsx(selected?.has(id) && "is-selected")}
                onClick={() => onRowClick?.(row)}
                style={{ cursor: onRowClick ? "pointer" : undefined }}
              >
                {renderCells(row)}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
