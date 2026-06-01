/** 数据展示组件 - Metric, ResourceList, EmptyText */

"use client";

export function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-lg border border-[#dfe4ee] bg-white px-3 py-2">
      <div className="text-xs text-[#667085]">{label}</div>
      <div className="text-lg font-semibold text-[#172033]">{value}</div>
    </div>
  );
}

export function ResourceList({ items }: { items: string[] }) {
  if (items.length === 0) return <EmptyText text="暂无数据。" />;
  return (
    <ul className="mt-3 space-y-2">
      {items.map((item) => (
        <li
          key={item}
          className="overflow-hidden text-ellipsis whitespace-nowrap rounded-lg border border-[#dfe4ee] bg-[#f8fafc] px-3 py-2 text-sm text-[#344054]"
        >
          {item}
        </li>
      ))}
    </ul>
  );
}

export function EmptyText({ text }: { text: string }) {
  return (
    <p className="rounded-lg border border-dashed border-[#dfe4ee] bg-[#f8fafc] px-3 py-3 text-sm text-[#667085]">
      {text}
    </p>
  );
}
