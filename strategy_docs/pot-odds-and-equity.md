# Pot odds, equity, outs and implied odds

This is a working reference for heads-up No-Limit Hold'em (HUNL). Effective stacks ~100bb, small blind = button (SB acts first preflop, last postflop). Blinds are 0.5bb / 1bb. All sizings are in big blinds (bb) and pot fractions. Use these formulas to turn a poker decision into arithmetic.

## Pot odds: the price you are paying

Pot odds are the price of a call relative to what you can win.

`pot odds = call cost / (pot before your call + call cost)`

This yields the **break-even equity**: the minimum share of the pot you must win for calling to beat folding.

- Villain bets 4bb into a 6bb pot. Pot before your call = 6 + 4 = 10bb. Call cost = 4bb. Total after call = 14bb.
- Break-even equity = 4 / 14 = **28.6%**. If your hand wins more than ~29% of the time, calling is profitable.

Common bet-size shortcuts (break-even equity to call):

- Bet 1/3 pot → need ~20%
- Bet 1/2 pot → need ~25%
- Bet 2/3 pot → need ~28.5%
- Bet 3/4 pot → need ~30%
- Bet full pot → need ~33%
- Bet 2x pot (overbet) → need ~40%

Bigger bets demand more equity. Memorize the half-pot and pot lines; interpolate the rest.

## Counting outs

An **out** is a card that improves you to a hand you believe will win. Count clean outs only; discount cards that could make villain a better hand.

Typical out counts (HU, where ranges are wide so draws often play to win):

- Flush draw: 9 outs
- Open-ended straight draw (OESD): 8 outs
- Gutshot: 4 outs
- Two overcards: ~6 outs (discount to ~3-4 if villain likely has a pair)
- Flush draw + OESD ("combo draw"): up to 15 outs
- Set-to-full-house/quads: ~7 outs
- One overcard + gutshot: ~6 outs

Subtract "dirty" outs: a card that pairs the board may give villain a full house; an offsuit straight card may complete villain's flush.

## Rule of 2 and 4

Convert outs to approximate equity fast:

- **Rule of 2**: outs x 2 = % to hit on the *next single card* (flop→turn, or turn→river).
- **Rule of 4**: outs x 4 = % to hit *across two cards* (flop→river), valid only when you are all-in on the flop or guaranteed to see both cards.

Examples:

- Flush draw on the flop, one card to come: 9 x 2 = **18%**.
- Flush draw on the flop, both cards (all-in): 9 x 4 = **36%** (true value ~35%).
- Gutshot, one card: 4 x 2 = **8%**.
- Combo draw all-in on flop: 15 x 4 = **60%** — you are the favorite.

For 9+ outs the rule of 4 slightly overstates; shave a couple points (e.g. 12 outs → ~45%, not 48%).

## Equity vs pot odds: the decision

Compare your **equity** (chance to win) against the **break-even equity** from pot odds. Call if equity ≥ break-even.

- Flop: 12bb pot. Villain bets 6bb. You hold a flush draw (9 outs).
- Pot odds: 6 / (12 + 6 + 6) = 6 / 24 = **25%** break-even.
- Your equity (one card to come): 9 x 2 = **18%**.
- 18% < 25% → a pure call **loses** on immediate odds. You need extra money later (implied odds) or fold equity from raising.

When your equity clears the price outright, just call (or raise for value/protection).

## Implied odds

Implied odds add the chips you expect to win *on later streets* when you hit. Effective pot odds become:

`call cost / (current pot + call cost + expected future winnings)`

In the flush-draw example, you needed 25% but had 18%. The gap is 7% of a 24bb pot ≈ 1.7bb shortfall per street. If hitting your flush lets you extract well over that from villain's stack on the turn/river, the call becomes +EV. With 100bb stacks, deep money makes drawing cheaper to justify — especially with **disguised, nutted** draws (sets, nut flush draws) that get paid.

## Reverse-implied odds

The mirror risk: when calling, you may make a second-best hand and *lose more* on later streets. Weak top pairs, dominated draws (low flush draw vs possible higher flush, bottom end of a straight) carry reverse-implied odds. Discount these hands — pay a worse price than the raw pot odds suggest, or fold marginal spots out of position.

## Expected value (EV) of a decision

EV ties it together:

`EV(call) = (equity x amount won) - ((1 - equity) x amount lost)`

- Pot 12bb, villain bets 6bb, you call 6bb. Win 18bb (pot + bet), lose your 6bb. Equity 35% (all-in flush draw, both cards).
- EV = (0.35 x 18) - (0.65 x 6) = 6.3 - 3.9 = **+2.4bb**. Call.

If a decision is close, choose the line whose EV is highest, not merely positive. Raising can win immediately via fold equity: `EV(raise) ≈ fold% x current pot + (1 - fold%) x EV(called)`.

## Quick rules

- Compute break-even equity first: `call / (pot + call)`. Then ask "do I have it?"
- Half-pot bet → need 25%; pot-sized → need 33%; overbet → need 40%+.
- Rule of 2 for one card, Rule of 4 only when going all-in / seeing both cards.
- Flush draw = 9 outs (~18% one card); OESD = 8 (~16%); gutshot = 4 (~8%).
- If raw equity falls short, only call when implied odds (deep stacks, nutted draw) cover the gap.
- Fold dominated/second-best draws — reverse-implied odds make the real price worse than it looks.
- When in doubt, pick the highest-EV action; fold equity often beats a thin call.
