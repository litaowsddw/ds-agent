"use client";

import { useEffect, useRef } from "react";

export interface ContextMenuItem {
  icon?: React.ReactNode;
  label: string;
  danger?: boolean;
  onSelect: () => void;
}

/**
 * Minimal anchored context menu (Dify *-contextmenu pattern): rendered inside
 * the canvas wrapper, closed by outside click, Escape, or any item action.
 */
export default function CanvasContextMenu({
  anchor,
  items,
  onClose,
}: {
  anchor: { x: number; y: number };
  items: ContextMenuItem[];
  onClose: () => void;
}) {
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const handlePointerDown = (event: PointerEvent) => {
      if (!menuRef.current?.contains(event.target as globalThis.Node)) onClose();
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("pointerdown", handlePointerDown, true);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown, true);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose]);

  return (
    <div
      className="absolute z-40 min-w-44 rounded-lg border border-[#dfe4ee] bg-white py-1 shadow-xl"
      ref={menuRef}
      role="menu"
      style={{ left: anchor.x, top: anchor.y }}
    >
      {items.map((item) => (
        <button
          className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs transition ${
            item.danger ? "text-[#b42318] hover:bg-[#fef3f2]" : "text-[#344054] hover:bg-[#f8fafc]"
          }`}
          key={item.label}
          onClick={() => {
            item.onSelect();
            onClose();
          }}
          role="menuitem"
          type="button"
        >
          {item.icon}
          {item.label}
        </button>
      ))}
    </div>
  );
}
