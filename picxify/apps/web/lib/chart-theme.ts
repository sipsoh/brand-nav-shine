/**
 * Chart theming: light values are baked into the ECharts option server-side
 * (app/services/chart_builder.py). Dark mode is applied here, at render time,
 * the same way withCompactFormatting works — the spec stays pure light-mode
 * JSON and a presentational transform swaps in the *validated* dark steps
 * (docs/engineering/design-system.md, dataviz skill references/palette.md),
 * never a mathematical inversion of the light ones.
 */

// Chrome & ink tokens (light -> dark), from design-system.md.
const CHROME: [string, string][] = [
  ["#fcfcfb", "#1a1a19"], // chart surface
  ["#e1e0d9", "#2c2c2a"], // gridline
  ["#c3c2b7", "#383835"], // baseline / axis
  ["#898781", "#898781"], // muted ink (unchanged)
  ["#52514e", "#c3c2b7"], // secondary ink
  ["#0b0b0b", "#ffffff"], // primary ink
  ["#006300", "#0ca30c"], // delta good
];

// Categorical palette, slot order fixed (chart_builder.py PALETTE).
const CATEGORICAL: [string, string][] = [
  ["#2a78d6", "#3987e5"],
  ["#1baf7a", "#199e70"],
  ["#eda100", "#c98500"],
  ["#008300", "#008300"],
  ["#4a3aa7", "#9085e9"],
  ["#e34948", "#e66767"],
  ["#e87ba4", "#d55181"],
  ["#eb6834", "#d95926"],
];

// Ordinal ramp for ordered stages (chart_builder.py ORDINAL_BLUES). The dark
// steps stay no darker than sequential-scale step 600 (#184f95, 2.15:1 vs the
// dark surface) per the palette reference — going further (step 650/700)
// fails the light-end-contrast check. The middle step intentionally targets
// the same dark hex as the categorical slot-1 blue (#3987e5): the light
// source hex (#2a78d6) is already shared between the two roles, so the dark
// target must be too, or a single hex would need two different remaps.
const ORDINAL: [string, string][] = [
  ["#86b6ef", "#cde2fb"],
  ["#5598e7", "#9ec5f4"],
  ["#2a78d6", "#3987e5"],
  ["#1c5cab", "#256abf"],
  ["#104281", "#184f95"],
];

const DARK_BY_LIGHT: Record<string, string> = Object.fromEntries(
  [...CHROME, ...CATEGORICAL, ...ORDINAL].map(([light, dark]) => [light.toLowerCase(), dark])
);

const DARK_TOOLTIP = {
  backgroundColor: "#1a1a19",
  borderColor: "#2c2c2a",
  textStyle: { color: "#ffffff" },
};
const LIGHT_TOOLTIP = {
  backgroundColor: "#fcfcfb",
  borderColor: "#e1e0d9",
  textStyle: { color: "#0b0b0b" },
};

function remapHexStrings(value: unknown): unknown {
  if (typeof value === "string") {
    return DARK_BY_LIGHT[value.toLowerCase()] ?? value;
  }
  if (Array.isArray(value)) return value.map(remapHexStrings);
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [key, val] of Object.entries(value)) out[key] = remapHexStrings(val);
    return out;
  }
  return value;
}

/** Applies the validated dark steps in place of the light ones baked into
 * the spec's echartsOption. No-op in light mode. */
export function applyChartTheme(
  option: Record<string, unknown>,
  mode: "light" | "dark"
): Record<string, unknown> {
  const themed = mode === "dark" ? (remapHexStrings(option) as Record<string, unknown>) : { ...option };
  themed.tooltip = { ...(themed.tooltip as object), ...(mode === "dark" ? DARK_TOOLTIP : LIGHT_TOOLTIP) };
  return themed;
}
