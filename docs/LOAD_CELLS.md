# Choosing Load Cells

The monitor asks two things of its load cells, and they pull in opposite
directions:

1. **Strong enough** to take the heaviest realistic hit — a cat landing
   off-center — without damage.
2. **Fine enough** that the HX711 can still resolve the grams-level
   variance [PoopSense](POOPSENSE.md) classifies on.

Oversizing feels safe but silently costs the second one: every kilogram
of rated capacity you don't need makes each ADC count coarser. This guide
gives you a capacity floor from the physics and a resolution ceiling from
the classifier — pick something between them.

## The Capacity Floor

Add up everything the cells will ever carry, with headroom:

> (baseboard + litterbox + litter + (heaviest cat × jump factor)) × 1.5

Pick the **jump factor** to match your cat, not the worst cat imaginable.
Measured landing forces for cats run about 1.5-3× body weight:

| Jump factor | Your cat |
|---|---|
| × 1.5 | Gentle stepper — walks in, or a low-sided box |
| × 2 | Typical — hops the rim with some enthusiasm |
| × 3 | Launcher — dives in from the nearest furniture |

The fixed **× 1.5** covers off-center loading. The four corners share the
load evenly only when it's centered; a cat landing near one corner can
push close to half the total force through a single cell.

Divide the result by four for the per-cell rating.

Don't pad beyond this. Hits rarer and harder than the formula assumes
land within the cells' safe-overload rating (typically 120-150% of
capacity) — a third layer of protection that's already in the hardware.

## Worked Examples

- **Average cat, typical jumper:** (1 kg baseboard + 0.5 kg box +
  2.5 kg litter + (5 kg cat × 2)) × 1.5 = **21 kg** total →
  four 6-8 kg cells (24-32 kg combined).
- **Large gentle cat, XL box:** (5 kg baseboard + 1.5 kg box +
  5 kg litter + (10 kg cat × 1.5)) × 1.5 ≈ **40 kg** total →
  four 10 kg cells (40 kg combined). Note the shelf: a KOMPLEMENT
  baseboard weighs 5.1 kg on its own and eats real margin.
- **Same cat, launcher habits (× 2):** ≈ **47 kg** total → four 12.5 kg
  cells (50 kg combined). At that rating, resolution gets borderline at
  3.3 V excitation, so this is the setup where a 5 V-capable HX711 board
  stops being optional (see the table below).

For reference, the development build — 6.5 kg non-jumping cat, 1.35 kg
box, 6 kg litter, 5.1 kg KOMPLEMENT shelf — comes out at ≈33 kg with the
× 1.5 factor. It has run on four 8 kg cells (32 kg combined) for two
years of daily use.

## The Resolution Ceiling

Presence detection and plain weight tracking work on almost any sensibly
sized cells. Waste-type classification doesn't: PoopSense separates
urination from defecation on roughly **0.5 g** of standard-deviation
daylight (see [its write-up](POOPSENSE.md#load-cell-selection) for where
that number comes from), so quantization matters. Rule of thumb:

- **<= 0.25 g/count**: plenty of room
- **0.25-0.5 g/count**: workable, tighter on edge cases
- **> 0.5 g/count**: too coarse — the classifier starts guessing

### Resolution Table

For common 4-cell bridge configurations. **g/count** values below are
**ballparks** (typical cheap cells, HX711 gain 128, real-world usable
20-bit resolution):

| Cell Rating | g/count @ 3.3V | Verdict @ 3.3V | g/count @ 5V | Verdict @ 5V |
|---|---|---|---|---|
| 4× 5kg = 20kg | ~0.12 | ✅ | ~0.08 | ✅ |
| 4× 8kg = 32kg | ~0.19 | ✅ | ~0.12 | ✅ |
| 4× 10kg = 40kg | ~0.23 | ✅ | ~0.15 | ✅ |
| 4× 12.5kg = 50kg | ~0.29 | ⚠️ borderline | ~0.19 | ✅ |
| 4× 20kg = 100kg | ~0.58 | ❌ | ~0.38 | ⚠️ borderline |
| 4× 50kg = 200kg | ~1.2 | ❌ | ~0.76 | ❌ |

"Bigger load cells just to be safe" eventually works against you: you
need cells rated high enough for the cat, the litter, and the box — but
not so high that the ADC can't resolve a few grams of variance. If the
floor and the ceiling leave you squeezed, running the cells at 5 V
excitation (with a properly isolated HX711 board — see the README's
hardware notes) buys the extra headroom.

## The Calibration Weight

Half-bridge cells are linear in the middle of their range and go wonky
near both ends. A reference weight that's small relative to the range —
say 4-5 kg on a 40 kg system — fits the calibration slope in a region
the scale never uses day to day, then extrapolates it out to where box +
litter + cat actually live. Aim the reference at the everyday load
instead, landing the scale mid-range where it's linear.

To build a 20 kg reference at gram accuracy, use several small water
bottles rather than one big jug. The kitchen scale you measure them with
has the same end-of-range problem, so weigh 2 L bottles two at a time on
a "5 kg max" scale and sum the batches. The development build was
calibrated this way, with ~20 kg of bottles.
