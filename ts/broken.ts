// Deliberate type errors for the compile-error scenario.
export function total(items: { price: number }[]): number {
  return items.reduce((sum, item) => sum + item.cost, 0);
}

const count: number = "three";
