const nodes = [
  { id: 'entity', label: 'Entity', detail: 'canonical subject', x: 74, y: 82, color: '#76910a' },
  { id: 'fact', label: 'Fact', detail: 'subject · attribute · value', x: 224, y: 82, color: '#248b65' },
  { id: 'source', label: 'Evidence', detail: 'source row · date', x: 374, y: 82, color: '#64748b' },
  { id: 'target', label: 'Entity', detail: 'name-valued target', x: 524, y: 38, color: '#76910a' },
  { id: 'targetfact', label: 'Fact', detail: 'verified · same date', x: 524, y: 126, color: '#248b65' },
];

const edges = [
  { from: 'entity', to: 'fact', label: 'indexed by subject', x: 149, y: 67 },
  { from: 'fact', to: 'source', label: 'source row', x: 299, y: 67 },
  { from: 'fact', to: 'target', label: 'verified relation', x: 411, y: 40 },
  { from: 'target', to: 'targetfact', label: 'same date', x: 581, y: 84 },
];

export default function TemporalGraphPreview() {
  const byId = Object.fromEntries(nodes.map((node) => [node.id, node]));

  return (
    <section aria-labelledby="temporal-graph-title" className="mt-3 rounded-2xl border border-black/[0.08] bg-white p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h4 id="temporal-graph-title" className="font-display text-[12px] font-bold text-[#202020]">Temporal evidence graph</h4>
          <p className="mt-0.5 text-[10px] text-black/55">How branch records connect</p>
        </div>
        <span className="rounded-full border border-[#76910a]/25 bg-[#76910a]/[0.07] px-2 py-1 text-[9px] font-semibold text-[#52670a]">Model view</span>
      </div>
      <div className="mt-3 overflow-x-auto">
        <svg viewBox="0 0 598 164" role="img" aria-label="Entity node indexed to a fact record, linked to its source evidence. Verified name relations can join a target entity to a fact observed on the same day." className="mx-auto block h-auto w-full max-w-[620px]">
          {edges.map(({ from, to, label, x, y }) => {
            const a = byId[from];
            const b = byId[to];
            return (
              <g key={`${from}-${to}`}>
                <line x1={a.x + 37} y1={a.y} x2={b.x - 37} y2={b.y} stroke="#69736b" strokeWidth="1.5" />
                <text x={x} y={y} textAnchor="middle" fill="#39443b" fontSize="8.5">{label}</text>
              </g>
            );
          })}
          {nodes.map((node) => (
            <g key={node.id}>
              <circle cx={node.x} cy={node.y} r="37" fill={node.color} />
              <text x={node.x} y={node.y - 3} textAnchor="middle" fill="white" fontSize="10" fontWeight="700">{node.label}</text>
              <text x={node.x} y={node.y + 10} textAnchor="middle" fill="white" fontSize="7.5">{node.detail}</text>
            </g>
          ))}
        </svg>
      </div>
      <div className="flex flex-wrap justify-center gap-x-4 gap-y-1 text-[9px] text-black/65" aria-label="Graph legend">
        <span><i className="mr-1 inline-block h-2 w-2 rounded-full bg-[#76910a]" />Entity</span>
        <span><i className="mr-1 inline-block h-2 w-2 rounded-full bg-[#248b65]" />Fact record</span>
        <span><i className="mr-1 inline-block h-2 w-2 rounded-full bg-[#64748b]" />Source row</span>
      </div>
      <p className="mt-2 text-center text-[9px] leading-relaxed text-black/50">Relation and event links are derived by same-day queries; observation dates do not prove continuous validity.</p>
    </section>
  );
}
