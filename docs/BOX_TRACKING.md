# Box Tracking

PoopSense figures out what the cat did. Box tracking figures out what *you*
did: scooped, topped up, deep cleaned, or picked the whole thing up to clean
under it. Each of those leaves a shape in the weight signal that a cat can't
make, and the firmware uses them to keep the litter and waste counters right
without being told.

## How it works

Everything runs on the **absolute** weight (calibrated, not tared), so the
bare board reads 0 g and an empty box reads "Empty Box Weight". That makes
the shapes unambiguous where event-relative deltas aren't:

| absolute reading | meaning |
|---|---|
| below -1 kg | whole monitor is in the air (frame hanging from the cells) |
| within 300 g of zero, stable | bare board, box is off |
| within 150 g of Empty Box Weight, stable, after the box was off | box came back empty |
| rising in steps, then dead still | litter poured in |

The other trick is telling litter from a cat without knowing what either
weighs: **nothing alive holds a 1 s standard deviation under 1 g for 30 s**.
The stillest cat in the recorded visits managed 11 s. Poured litter holds it
forever. So a rise that stays inert for 30 s is litter, even if the bag
happens to weigh exactly what your cat does.

`BoxMonitor` in [state_analyzer.h](../state_analyzer.h) sees every sample,
not just during events, because the interesting moments straddle event
boundaries (box leaves in one event, comes back in the next). It tracks two
things:

- **Box state:** `normal`, `lifted`, `off` or `empty`, from the table above.
  `off` and `empty` need the level held for 3 s. Absence latches: once the
  box is gone it stays gone until something stable shows up on the board
  again, and the tare is held the whole time.
- **Plateaus:** every stretch of at least 2 s with σ < 15.8 g, as mean,
  length and sigma. The classifier reads an event as a ladder of plateaus.

### The verdict

When an event ends, before the tare moves, the first rule that fits wins:

1. **Box still absent.** No verdict yet. Tare stays where it was.
2. **Box came back empty** (within 150 g of Empty Box Weight, with its lid
   or, if Lid Weight is set, without it; held 3 s)
   → `deep_clean`. Litter weight becomes whatever has gone in since, waste
   and visits reset, deep-clean timer restarts.
3. **Monitor lifted and set back** within 100 g of where it was → `lifted`.
4. **Box off and back** between -20 g and +100 g of where it was → `lifted`.
5. **Plateaus never drop** (by more than 50 g) from the lowest point of the
   event, at least 300 g gained, last 30 s inert → `top_up`, measured from
   that lowest point. If the lowest point is a scoop's worth below where the
   event started, a `scoop` is reported alongside.
6. **At least 20 g lighter, no cat matched**, and either the event ran 30 s,
   the box left the board, or its lid came off → `scoop`.

With a Lid Weight set, every level in these rules is taken as if the lid
were on (see [Boxes with a lid](#boxes-with-a-lid)).

Otherwise it's a plain cat visit (or nothing). A maintenance verdict
overrides the cat analysis: if a bag went inert on the scale, it was a bag,
whatever the weight matcher thought.

A rise that goes inert also ends the event on the spot instead of waiting
for the inactivity timeout.

### Zero check

Whenever the box is off and the bare board holds stable for 3 s, whatever it
reads is drift, and it gets folded into the calibration offset. Published as
"Zero Drift". Only the zero moves, the span still comes from calibration. A
board more than 300 g from zero is left alone on the assumption something
is wedged under it.

### Boxes with a lid

A top-entry box has a lid that comes off to scoop or pour. Without knowing
it, the tracker reads the lid coming off as litter leaving: a top-up is
measured from the lowest point, which is the box without its lid, so Litter
Added comes out a lid too high and a scoop is reported alongside. And if the
event ends while the lid is off, the scale tares there and the lid going
back on lands in Waste Weight.

Set the lid's weight in Lid Weight, next to Empty Box Weight (0, the
default, is no lid). Empty Box Weight is then the box with its lid on. The
lid comes off and goes back as one step of about that weight between steady
levels, where a scoop comes out in small drops and litter pours in as a
ramp, so a step within `lid_tolerance` (30 g) of it is the lid. A lid's
weight doesn't change the way a cat's does, so the window is fixed, like the
empty box's, rather than a share of it. Every level measured with the lid
off is counted as if it were on, the lid's state carries over into the next
event, and taking it off counts as opening the box, like lifting the box off
(no minimum duration for a scoop). An empty box also counts for a deep clean
with its lid on or off.

The lid has to sit still, off or on, for about two seconds to be seen: a
lid lifted and put straight back is just a wobble, which is harmless. Keep
the box and lid clear of walls: a lid catching on one moved the reading by
up to 30 g, where clear of it the level with the lid on came back within a
couple of grams.

All thresholds are substitutions at the top of the YAML:
`box_off_tolerance`, `box_empty_tolerance`, `monitor_lift_threshold`,
`lift_return_tolerance`, `min_top_up_weight`, `top_up_settle_time`,
`lid_tolerance`, plus `min_clean_event_weight` and `min_clean_event_duration`
for scoops.

## Troubleshooting

Most of these come down to the tracker only having one signal to work with.
It can't see hands, scoops or bags, only mass and stillness, so a few
ordinary things look the same to it.

**Scoop not registering.** The event ran under 30 s and the box stayed on
the board, so the tracker can't tell it from a bump. The scale is still
tared afterwards, nothing accumulates wrongly, but the counters don't reset.
Lower `min_clean_event_duration`, or lift the box while scooping: an absence
is proof enough and the duration requirement goes away.

**Scoop not registering, small amount.** Less than 20 g came out, which is
below the floor for a scoop. `min_clean_event_weight` sets it.

**Scoop logged after just moving the box.** The box came back more than
20 g lighter. Litter clings to the rim, sticks to the scoop, gets kicked out
in transit, and 20 g is not much. This is the scoop floor firing, not the
lift tolerance, so `min_clean_event_weight` is the knob to raise.

**Top-up not registering.** Three common causes:

- The last 30 s of the event weren't inert. Leveling, stirring or tapping the
  box keeps the signal moving, and stillness is the only thing that proves a
  bag isn't a cat. The pour needs a quiet 30 s after it.
- Something over 50 g came off after the pour, such as a scoop that was
  resting on the rim. The plateau ladder has to stay monotonic from its
  lowest point, so that drop disqualifies it.
- Less than 300 g went in. `min_top_up_weight`.

**Top-up amount looks wrong.** It's measured from the lowest plateau in the
event, not from where the event started, so scooping before the pour isn't
subtracted from the bag. A `scoop` event fires alongside when that happens.

**Top-up logged with nobody near the box.** Something inert sat on it for
30 s: a bag on the lid, the scoop on the rim. To the tracker that is
indistinguishable from litter. Removing it again reads as a scoop.

**Visit vanished, top-up logged instead.** The pour started within a few
seconds of the cat leaving, before the event closed, so both landed in one
event and the maintenance verdict took precedence. Waiting for the state to
read "empty" before refilling keeps them apart.

**Deep clean not detected.** In order of likelihood:

- Empty Box Weight isn't set. The tracker still sees the box leave and
  return but has no way to tell an empty box from a scooped-down one.
- The box came back with something in it: the scoop, a bag, a liner. More
  than 150 g over the empty weight reads as "not empty".
- Litter went in less than 3 s after the box was set down. The empty level
  has to hold for 3 s to register, and a pour starting before that erases
  it.
- Empty Box Weight is stale. A washed box weighing a few grams more wet is
  within the 150 g tolerance; a different box or a heavy new liner may not
  be.

**Deep clean detected, timer didn't restart.** The clock wasn't synced at
the time (the log says "Deep clean not stamped"). Counters still reset,
only the date is skipped.

**Zero Drift jumps around.** The zero check fires whenever the bare board
holds still within 300 g, and it takes whatever is there as the new zero. A
lid, a mat or a hand resting on the board while the box is off gets folded
into the offset. If it has drifted, re-running calibration resets it.

**Everything reads "lifted".** The absolute weight is below -1 kg, which
the tracker interprets as the frame hanging from the cells. With the box
off the raw reading should be near zero; if it isn't, suspect a cell or the
calibration offset.

**Boot with the box off.** The state reads `normal` for the first second
regardless, until the stability window fills. Harmless; the first log line
just isn't meaningful.
