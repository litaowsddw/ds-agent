"use client";

import { PanelLeft, PanelRight, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

type MobilePanel = "palette" | "inspector";

export default function WorkflowResponsiveLayout({
  canvas,
  inspector,
  palette,
}: {
  canvas: React.ReactNode;
  inspector: React.ReactNode;
  palette: React.ReactNode;
}) {
  const [mobilePanel, setMobilePanel] = useState<MobilePanel | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const closePanel = useCallback(() => setMobilePanel(null), []);

  useEffect(() => {
    if (!mobilePanel) return;
    returnFocusRef.current = document.activeElement as HTMLElement | null;
    const dialog = dialogRef.current;
    const focusable = getFocusableElements(dialog);
    (focusable[0] ?? dialog)?.focus();
    document.body.style.overflow = "hidden";

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        closePanel();
        return;
      }
      if (event.key !== "Tab") return;
      const elements = getFocusableElements(dialog);
      if (elements.length === 0) {
        event.preventDefault();
        dialog?.focus();
        return;
      }
      const first = elements[0];
      const last = elements[elements.length - 1];
      if (event.shiftKey && (document.activeElement === first || !dialog?.contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "";
      returnFocusRef.current?.focus();
    };
  }, [closePanel, mobilePanel]);

  const label = mobilePanel === "palette" ? "Nodes" : "Workflow & inspector";
  const panelId = mobilePanel === "palette" ? "workflow-mobile-palette" : "workflow-mobile-inspector";
  const panelContent = mobilePanel === "palette" ? palette : inspector;

  return (
    <div>
      <div
        className="grid h-[calc(100dvh-5rem)] min-h-[620px] min-w-0 grid-rows-[auto_minmax(0,1fr)] gap-3 sm:h-[calc(100dvh-7rem)] sm:min-h-[720px] sm:gap-4 xl:grid-cols-[280px_minmax(0,1fr)_400px] xl:grid-rows-1"
        data-testid="workflow-responsive-background"
        inert={mobilePanel ? true : undefined}
      >
        <div className="flex items-center gap-2 xl:hidden">
          <DrawerTrigger
            controls="workflow-mobile-palette"
            expanded={mobilePanel === "palette"}
            icon={<PanelLeft size={14} />}
            label="Nodes"
            onClick={() => setMobilePanel("palette")}
          />
          <DrawerTrigger
            controls="workflow-mobile-inspector"
            expanded={mobilePanel === "inspector"}
            icon={<PanelRight size={14} />}
            label="Workflow & inspector"
            onClick={() => setMobilePanel("inspector")}
          />
        </div>

        <aside className="hidden min-h-0 overflow-hidden rounded-lg border border-[#dfe4ee] bg-white xl:col-start-1 xl:row-start-1 xl:block">
          {palette}
        </aside>
        <main className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-lg border border-[#dfe4ee] bg-white xl:col-start-2 xl:row-start-1">
          {canvas}
        </main>
        <aside className="hidden min-h-0 space-y-4 overflow-y-auto xl:col-start-3 xl:row-start-1 xl:block">
          {inspector}
        </aside>
      </div>

      {mobilePanel ? (
        <div className="fixed inset-0 z-20 xl:hidden">
          <button
            aria-label="Close workflow drawer"
            className="absolute inset-0 bg-[#172033]/35"
            onClick={closePanel}
            tabIndex={-1}
            type="button"
          />
          <div
            aria-label={label}
            aria-modal="true"
            className={`absolute bottom-3 top-[4.25rem] z-10 w-[min(400px,calc(100vw-1.5rem))] overflow-y-auto rounded-lg bg-[#f6f7f9] shadow-xl ${
              mobilePanel === "palette" ? "left-3 max-w-[280px]" : "right-3"
            }`}
            id={panelId}
            ref={dialogRef}
            role="dialog"
            tabIndex={-1}
          >
            <div className="sticky top-0 z-10 flex items-center justify-between border-b border-[#dfe4ee] bg-white px-4 py-2">
              <span className="text-sm font-semibold text-[#172033]">{label}</span>
              <button
                aria-label={`Close ${label}`}
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-[#667085] hover:bg-[#f8fafc]"
                onClick={closePanel}
                type="button"
              >
                <X size={16} />
              </button>
            </div>
            {panelContent}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function DrawerTrigger({
  controls,
  expanded,
  icon,
  label,
  onClick,
}: {
  controls: string;
  expanded: boolean;
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      aria-controls={controls}
      aria-expanded={expanded}
      className="inline-flex items-center justify-center gap-1 rounded-lg border border-[#cfd7e6] bg-white px-2 py-2 text-xs font-medium text-[#172033] transition hover:border-[#2f6feb]"
      onClick={onClick}
      type="button"
    >
      {icon}
      {label}
    </button>
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
