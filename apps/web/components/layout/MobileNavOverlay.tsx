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
  const drawerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    returnFocusRef.current = document.activeElement as HTMLElement | null;
    const drawer = drawerRef.current;
    const focusable = getFocusableElements(drawer);
    (focusable[0] ?? drawer)?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const elements = getFocusableElements(drawer);
      if (elements.length === 0) {
        event.preventDefault();
        drawer?.focus();
        return;
      }
      const first = elements[0];
      const last = elements[elements.length - 1];
      if (event.shiftKey && (document.activeElement === first || !drawer?.contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
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
        tabIndex={-1}
        type="button"
      />
      <div
        aria-label="Navigation"
        aria-modal="true"
        className={`relative h-full w-[min(320px,85vw)] transform bg-white shadow-xl transition-transform ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
        ref={drawerRef}
        role="dialog"
        tabIndex={-1}
      >
        <Sidebar inactive={!open} mobile onNavigate={onClose} />
      </div>
    </div>
  );
}

function getFocusableElements(container: HTMLElement | null): HTMLElement[] {
  if (!container) return [];
  return Array.from(
    container.querySelectorAll<HTMLElement>(
      'a[href]:not([tabindex="-1"]), button:not([disabled]):not([tabindex="-1"]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )
  );
}
