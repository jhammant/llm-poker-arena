# Bet and raise sizing

This primer is for heads-up No-Limit Hold'em, ~100bb effective, small blind on the button. All sizes are stated as a fraction of the current pot. Your job is to choose a size that maximizes value or fold equity *without telling your opponent what you hold*.

## The core sizing menu

Five reference sizes cover almost every spot:

- **1/3 pot (~33%)** — cheap probe. Pushes thin equity, denies free cards, keeps your bluffing range wide because the price you risk is low. Good on dry, static boards.
- **1/2 pot (~50%)** — the default "I have a reason to bet" size. Charges draws a fair price, builds the pot moderately.
- **2/3 pot (~66%)** — the workhorse value/bluff size on most dynamic boards. Strong fold equity, good pot growth.
- **Pot (100%)** — heavy pressure. Use when ranges are polarized and you want maximum value from strong made hands or maximum fold equity from bluffs.
- **Overbet (125%–200%)** — for very polarized spots, usually on later streets when your range is capped at the top by nutted hands and air, and theirs is full of bluff-catchers.

Bigger bets need fewer bluffs to stay balanced; smaller bets can carry many bluffs. The math: to make a bluff-catcher indifferent, your bluff frequency should be roughly bet / (bet + 2·bet)... in practical terms, a pot-sized bet wants ~1 bluff per 2 value hands; a half-pot bet wants ~1 bluff per 3 value hands.

## Value vs bluff sizing

A common leak is sizing by hand strength: big with the nuts, small with bluffs. Do the opposite of *predictable*. Pick a size based on **the board and the range you are representing**, then put both value hands and bluffs into that same size. If you only overbet your monsters, an opponent simply folds everything to your overbet and you never get paid.

Practical defaults:

- **Thin value** (a one-pair hand that wants calls from worse) prefers smaller sizes (1/3–1/2) so weaker hands continue.
- **Strong value** (two pair+) on a wet board prefers larger sizes (2/3–pot) because draws will pay and you want stacks in by the river.
- **Bluffs** should match whatever value size occupies that spot. Your best bluffs are hands with backdoor equity or blockers to the opponent's calls.

## Polarized vs merged ranges

- A **polarized** range is "nuts or nothing" — strong value plus bluffs, little in between. Polarized ranges use **large** sizes (pot, overbet). You are happy to fold out the middle and get called only by the parts of their range you beat or want to deny.
- A **merged** (or "linear") range is value-heavy and thin: strong, medium, and some weak-but-ahead hands. Merged ranges use **small** sizes (1/3–1/2) to get called by a wide span of worse hands.

Rule of thumb: when *you* are uncapped and *they* are capped, polarize and bet big. When you both have a lot of medium hands, merge and bet small.

## Sizing by street

- **Preflop:** Open the button to **2–2.5bb** (limp/raise mixes exist but a raise-first default is cleaner). Facing a 2.5bb open, **3-bet to ~9–10bb** in position is rare HU since SB acts first; out of position from the BB, 3-bet to **~10–12bb**. 4-bet to **~22–25bb**.
- **Flop:** On dry, range-advantaged boards (e.g., A-high), a small **1/3 c-bet at high frequency**. On wet, dynamic boards, fewer bets but **larger (2/3)**.
- **Turn:** Equities are clearer; sizes grow. Continuing barrels at **2/3–pot** as the range polarizes.
- **River:** Pure polarization. Value bets and bluffs only — choose **pot or overbet** when your range is uncapped, smaller when value is thin.

## Why consistent sizing matters

If your size leaks your holding, a thinking opponent (or solver-like agent) exploits it for free: folding to your "big = strong" bets and raising your "small = weak" ones. Consistency means the *same* size shows up with a deliberately mixed range, so no single action narrows your hand. Build size **buckets per board texture**, fill each bucket with the right value-to-bluff ratio, and stop adjusting size based on how much you like your cards.

## Worked examples

**Thin value, half pot.** Pot is 12bb on the turn, board K72r-9. You hold KJ. Bet **6bb (1/2)**. Worse kings and pairs call; you avoid bloating the pot against a better king.

**Polarized overbet, river.** Pot is 30bb, board AQ732 with a busted flush. You hold A7 (two pair) or 65 (missed draw). Bet **45bb (1.5x)** with *both*. The opponent's range is capped at one pair; the overbet maximizes value from A-x and folds out their floats. Mixing the bluff in at the right ratio (~1 bluff per 2 value) keeps you uncallable to exploit.

**Wet board, large flop bet.** Pot 6bb, flop JT9 two-tone. You hold Q8 (nut straight) or AcKc (combo draw). Bet **4bb (2/3)** with both — charge the many draws and grow the pot for stacks-in by the river.

## Quick rules

- Default to 2/3 pot when unsure; it balances value and fold equity.
- Use small (1/3–1/2) with merged, value-heavy ranges; large (pot+) with polarized ranges.
- Bigger bets need more value relative to bluffs; pot ≈ 2:1 value:bluff, half-pot ≈ 3:1.
- Overbet only when you are uncapped and they are capped.
- Never let size reveal strength — same size, mixed range, per board texture.
- Bet bigger on wet/dynamic boards, smaller on dry/static ones.
- Thin value wants small sizes; strong value on wet boards wants big sizes.
- Pick the size from the board and range you represent, not from how much you like your hand.
