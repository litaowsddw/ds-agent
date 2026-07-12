"use client";

import { useEffect, useRef } from "react";
import Sidebar from "./Sidebar";

export default function MobileNavOverlay({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const returnFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    returnFocusRef.current = document.activeElement as HTMLElement | null;
    const close = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    document.addEventListener("keydown", close);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", close);
      document.body.style.overflow = "";
      returnFocusRef.current?.focus();
    };
  }, [open, onClose]);

  return (
    <div
      aria-hidden={!open}
      className={`fixed inset-0 z-40 lg:hidden ${open ? "" : "pointer-events-none"}`}
      data-testid="mobile-navigation-overlay"
      id="mobile-navigation"
    >
      <button
        aria-label="Close navigation"
        className={`absolute inset-0 bg-[#172033]/40 transition-opacity ${open ? "opacity-100" : "opacity-0"}`}
        onClick={onClose}
        tabIndex={open ? 0 : -1}
        type="button"
      />
      <div
        className={`relative h-full w-[min(320px,85vw)] transform bg-white shadow-xl transition-transform ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <Sidebar mobile onNavigate={onClose} />
      </div>
    </div>
  );
}
