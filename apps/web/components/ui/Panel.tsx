/** Panel 卡片组件 - Dify 风格白色圆角卡片 */

"use client";

interface PanelProps {
  title: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
  actions?: React.ReactNode;
}

export default function Panel({ title, icon, children, actions }: PanelProps) {
  return (
    <section className="rounded-xl border border-[#dfe4ee] bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {icon && <span className="text-[#2f6feb]">{icon}</span>}
          <h3 className="text-sm font-semibold text-[#172033]">{title}</h3>
        </div>
        {actions}
      </div>
      {children}
    </section>
  );
}
