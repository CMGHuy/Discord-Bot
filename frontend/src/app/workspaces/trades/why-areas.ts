export type WhyCard = 'why' | 'scores' | 'sources' | 'breakdown' | 'gates' | 'context';
export const WHY_CARDS: readonly WhyCard[] = ['why', 'scores', 'sources', 'breakdown', 'gates', 'context'];
export interface CardAreas { one: string; two: string; three: string; }

export const OVERVIEW_AREAS: CardAreas = {
  one: '"plan" "position" "outcome"',
  two: '"plan position" "outcome outcome"',
  three: '"plan position outcome"',
};

function collapseRows(rows: readonly (readonly WhyCard[])[], present: ReadonlySet<WhyCard>): string {
  const filled = rows.map(row => {
    const remaining = row.filter(card => present.has(card));
    if (!remaining.length) return null;
    while (remaining.length < row.length) remaining.push(remaining[remaining.length - 1]);
    return `"${remaining.join(' ')}"`;
  }).filter(row => row !== null);
  return filled.join(' ') || 'none';
}

export function whyAreas(present: ReadonlySet<WhyCard>): CardAreas {
  return {
    one: collapseRows(WHY_CARDS.map(card => [card]), present),
    two: collapseRows([['why', 'why'], ['scores', 'context'], ['sources', 'sources'], ['breakdown', 'breakdown'], ['gates', 'gates']], present),
    three: collapseRows([['why', 'why', 'scores'], ['sources', 'sources', 'sources'], ['breakdown', 'breakdown', 'breakdown'], ['gates', 'gates', 'context']], present),
  };
}

export function areaStyle(areas: CardAreas): Record<string, string> {
  return { '--areas-1': areas.one, '--areas-2': areas.two, '--areas-3': areas.three };
}
