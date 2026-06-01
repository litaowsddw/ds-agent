/** 表单组件 - TextInput, TextArea, SelectInput */

"use client";

export function TextInput({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-xs font-medium text-[#667085]">{label}</span>
      <input
        className="w-full rounded-lg border border-[#dfe4ee] bg-white px-3 py-2 text-sm outline-none transition focus:border-[#2f6feb] focus:ring-1 focus:ring-[#2f6feb]/20"
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        type={type}
        value={value}
      />
    </label>
  );
}

export function TextArea({
  label,
  value,
  onChange,
  rows = 4,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  rows?: number;
  placeholder?: string;
}) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-xs font-medium text-[#667085]">{label}</span>
      <textarea
        className="w-full resize-y rounded-lg border border-[#dfe4ee] bg-white px-3 py-2 text-sm leading-6 outline-none transition focus:border-[#2f6feb] focus:ring-1 focus:ring-[#2f6feb]/20"
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        rows={rows}
        value={value}
      />
    </label>
  );
}

export function SelectInput({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<{ label: string; value: string }>;
}) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-xs font-medium text-[#667085]">{label}</span>
      <select
        className="w-full rounded-lg border border-[#dfe4ee] bg-white px-3 py-2 text-sm outline-none transition focus:border-[#2f6feb]"
        onChange={(e) => onChange(e.target.value)}
        value={value}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </label>
  );
}
