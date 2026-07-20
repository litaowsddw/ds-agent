"use client";

import { BookOpenCheck, CopyPlus, Sparkles } from "lucide-react";
import { WORKFLOW_TEMPLATES } from "@/components/workflows/workflowTemplates";
import type { WorkflowTemplate } from "@/types/workflow";

export default function WorkflowTemplateLibrary({
  onSelect,
}: {
  onSelect: (template: WorkflowTemplate) => void;
}) {
  return (
    <section aria-label="Workflow templates" className="rounded-lg border border-[#bfdbfe] bg-[#f8fbff]">
      <div className="flex items-start gap-2 border-b border-[#dbeafe] px-4 py-3">
        <Sparkles className="mt-0.5 shrink-0 text-[#2f6feb]" size={16} />
        <div>
          <div className="text-sm font-semibold text-[#172033]">从模板开始</div>
          <p className="mt-1 text-xs leading-5 text-[#475467]">
            复制一个可执行的起点到全新草稿。不会覆盖当前 Workflow，也不会改动任何已发布版本。
          </p>
        </div>
      </div>
      <div className="space-y-3 p-4">
        {WORKFLOW_TEMPLATES.map((template) => (
          <article key={template.id} className="rounded-lg border border-[#dfe4ee] bg-white p-3">
            <div className="flex items-start justify-between gap-2">
              <div>
                <h3 className="text-sm font-semibold text-[#172033]">{template.name}</h3>
                <p className="mt-1 text-xs leading-5 text-[#667085]">{template.description}</p>
              </div>
              <span className="shrink-0 rounded bg-[#eef4ff] px-2 py-1 text-[10px] font-semibold text-[#175cd3]">
                {template.category}
              </span>
            </div>
            <div className="mt-3 rounded-md bg-[#f8fafc] px-2.5 py-2">
              <div className="flex items-center gap-1.5 text-[11px] font-semibold text-[#475467]">
                <BookOpenCheck size={13} />
                创建后还需
              </div>
              <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[11px] leading-4 text-[#667085]">
                {template.setup.map((step) => <li key={step}>{step}</li>)}
              </ul>
            </div>
            <button
              className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-[#2f6feb] bg-white px-2.5 py-1.5 text-xs font-semibold text-[#175cd3] transition hover:bg-[#eef4ff]"
              onClick={() => onSelect(template)}
              type="button"
            >
              <CopyPlus size={14} />
              使用此模板
            </button>
          </article>
        ))}
      </div>
    </section>
  );
}
