"use client";

import { Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { NODE_PALETTE, type WorkflowPaletteItem } from "@/lib/constants";

/**
 * ComfyUI-style quick node picker: shown when a dragged connection lands on
 * empty canvas, on pane double-click, or from a node's hover "+" button.
 * Selecting an item creates the node (and wires it when a source is pending).
 */
export default function NodeQuickAddMenu({
  anchor,
  onClose,
  onSelect,
}: {
  /** Position (px) relative to the canvas wrapper. */
  anchor: { x: number; y: number };
  onClose: () => void;
  onSelect: (item: WorkflowPaletteItem) => void;
}) {
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  const items = useMemo(() => {
    const executable = NODE_PALETTE.filter((item) => item.capability === "executable");
    const term = query.trim().toLowerCase();
    if (!term) return executable;
    return executable.filter((item) =>
      `${item.label} ${item.description} ${item.type} ${item.group}`.toLowerCase().includes(term)
    );
  }, [query]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  useEffect(() => {
    listRef.current
      ?.querySelector(`[data-index="${activeIndex}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [activeIndex]);

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((index) => Math.min(index + 1, items.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((index) => Math.max(index - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      const item = items[activeIndex];
      if (item) onSelect(item);
    } else if (event.key === "Escape") {
      event.preventDefault();
      onClose();
    }
  };

  return (
    <div
      className="absolute z-30 w-64 rounded-xl border border-[#dfe4ee] bg-white shadow-xl"
      data-testid="node-quick-add-menu"
      style={{ left: anchor.x, top: anchor.y }}
    >
      <label className="flex h-10 items-center gap-2 border-b border-[#eef1f6] px-3 text-sm">
        <Search size={14} className="shrink-0 text-[#98a2b3]" />
        <input
          ref={inputRef}
          className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-[#98a2b3]"
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="搜索节点…"
          value={query}
        />
      </label>
      <div className="max-h-64 overflow-y-auto p-1.5" ref={listRef}>
        {items.length === 0 ? (
          <div className="px-3 py-4 text-center text-xs text-[#98a2b3]">没有匹配的节点</div>
        ) : null}
        {items.map((item, index) => (
          <button
            className={`flex w-full items-start gap-2 rounded-lg px-2.5 py-2 text-left ${
              index === activeIndex ? "bg-[#eef4ff]" : "hover:bg-[#f8fafc]"
            }`}
            data-index={index}
            key={item.type}
            onClick={() => onSelect(item)}
            onMouseEnter={() => setActiveIndex(index)}
            type="button"
          >
            <span className="min-w-0">
              <span className="block truncate text-sm font-medium text-[#172033]">{item.label}</span>
              <span className="block truncate text-xs text-[#667085]">{item.description}</span>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
