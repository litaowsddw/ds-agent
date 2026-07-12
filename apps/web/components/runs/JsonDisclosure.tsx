interface JsonDisclosureProps {
  label: string;
  value: unknown;
}

export default function JsonDisclosure({ label, value }: JsonDisclosureProps) {
  const content = value == null ? "—" : JSON.stringify(value, null, 2);

  return (
    <details className="rounded-lg border border-[#dfe4ee] bg-[#f8fafc]">
      <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-[#344054]">
        {label}
      </summary>
      <pre className="max-h-[280px] overflow-auto border-t border-[#dfe4ee] bg-[#0f172a] p-3 text-xs leading-5 text-[#dbeafe]">
        {content}
      </pre>
    </details>
  );
}
