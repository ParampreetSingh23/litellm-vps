import React from "react";
import { totalUnits, type UsageUnits } from "./usageUnits";

export function UnpricedNote({ unpriced }: { unpriced: UsageUnits }) {
  const total = totalUnits(unpriced);
  if (total === 0) return null;
  const [noun, verb] = total === 1 ? ["unit", "is"] : ["units", "are"];
  return (
    <p className="text-xs text-warning">
      {`${total.toLocaleString()} ${noun} with no known price ${verb} left out of the cost.`}
    </p>
  );
}
