# User-Supplied Reference Decks

Received 2026-10-11. Decklists are preserved as supplied; none of these cards
have been substituted. Winota's Alexios sideboard is excluded from the playable
deck. These lists are research references, not yet enabled external-agent decks.

The supplied Winota primer is credited in the pasted text to maratiam and titled
Winota Avalanche. No canonical deck URL or revision was supplied. The primer
contains historical recommendations and a changelog that do not exactly match
the pasted list; use the pasted list as the card snapshot and primer as strategy
context. This summary preserves testing ideas rather than treating every claim
as a verified current rule or recommendation.

Winota regression priorities:

- Non-Human attackers generate separate Winota triggers; Humans do not.
- Revealed Humans enter tapped and attacking, and require defender choices.
- Choices among revealed cards must not reveal the rest of a library to the policy.
- Rule-of-Law and Canonist restrictions affect casting, not all battlefield entries.
- Combat sequencing can change access to mana and spells when stax enters mid-combat.
- Token creation, battle cry, double strike, metalcraft, and player elimination
  need explicit state/decision coverage before evaluating this list.
- Combat Celebrant/Rionya lines need isolated rules tests before use as training goals.

The attached Yuriko primer is preserved separately as `yuriko_supplied.txt`.
Its author/revision/source URL were not provided. It describes early evasive
attackers, commander ninjutsu, Ninja combat-damage triggers, topdeck manipulation,
Oracle/Consultation/Pact lines, and Doomsday piles.

Yuriko regression priorities:

- Commander ninjutsu has different timing/cost behavior from normal casting.
- Each Ninja damage trigger produces a reveal/draw/life-loss sequence.
- Mana value for split and double-faced cards needs engine-derived features.
- Stack responses to triggers, alternative costs, tutors, library ordering,
  and extra turns need explicit decision support.
- Oracle wins and failed combo attempts need true terminal labels, not guessed outcomes.

Both deck counts and card support need machine validation. In particular,
`Samut, Tyrant of Naktamun` was initially flagged for investigation. The fetched
Scryfall snapshot identifies the supplied new card as blue, so the preflight
found no color-identity issue for this entry. The installed engine cannot load it.
Primers are reference material, not self-play trajectories or policy labels.

RogSi and Kinnan were supplied in a follow-up message. Their attached primers
are preserved as `rogsi_supplied.txt` (The EPIC Storm) and
`kinnan_supplied.txt` (FreedomWaffle), respectively. Canonical source URLs and
revision identifiers were not supplied. RogSi uses two explicit commanders;
Kinnan has one. Each deck contains exactly 100 playable cards, and Winota has
one additional sideboard card.

RogSi testing priorities include storm counting, Breach/LED/Brain Freeze lines,
Oracle and library-exile choices, sacrifice and alternative costs, wheel timing,
extra-turn loss triggers, and hidden-information-safe tutor choices. Kinnan
priorities include nonland mana replacement, Basalt Monolith loops, activated
commander choices, copying effects, library selection, and infinite-mana outlets.
These priorities guide future engine tests; none are implemented by the
land/pass bridge. Samut also appears in RogSi and Kinnan; the same engine gap applies.

Scryfall preflight on 2026-10-11 passed Yuriko, RogSi, and Kinnan's card-name,
Commander-legality, color-identity, count, and basic singleton checks. Winota
has unresolved exact names `Holga, Relentless Rager` and `Rick, Steadfast Leader`
in the fetched API response. RogSi's `Unstable Harmonics` resolves via named
lookup to a `Rhystic Study` printed-name alias. Original entries remain intact.
This preflight does not certify commander pairing, card-specific exceptions,
or gameplay support. Printing release dates are not first-appearance dates:
a new printing of Plains is not evidence that the engine lacks Plains.

Actual installed-engine audit results:

| Deck | Cards Loaded Including Commanders | Missing Names |
| --- | --- | --- |
| Winota | 97/100 | Holga, Relentless Rager; Rick, Steadfast Leader; Scuzzback Scrounger |
| Yuriko | 93/100 | Fblthp, Impossibly Lost; Irma, Part-Time Mutant; Samut, Tyrant of Naktamun; Splinter, Hamato Yoshi; Splinter's Technique; Stature, Size Shifter; Yuriko, Hope from the Shadows |
| RogSi | 97/100 | Hexing Squelcher; Samut, Tyrant of Naktamun; Unstable Harmonics |
| Kinnan | 97/100 | Pia, Aether Ascetic; Samut, Tyrant of Naktamun; Wan Shi Tong, Librarian |

All four fail the installed engine's deck-size validation because missing cards
are dropped by its importer. Their original files each contain 100 playable cards.
Scryfall recognizes most missing engine names; API legality is not engine support.
The engine/card snapshot needs updating or compatible card implementations before
these can be simulation baselines. No reference deck has been silently trimmed.

Reproduce the checks:

```powershell
.\.venv\Scripts\python.exe -m cedhai.audit_cards --decks examples/decks/reference/winota.txt examples/decks/reference/yuriko.txt examples/decks/reference/rogsi.txt examples/decks/reference/kinnan.txt --out runs/cards-new
.\.venv\Scripts\python.exe -m cedhai.audit_engine --decks examples/decks/reference/winota.txt examples/decks/reference/yuriko.txt examples/decks/reference/rogsi.txt examples/decks/reference/kinnan.txt --out runs/engine-new
```

The Scryfall command saves a timestamped snapshot and supports `--snapshot`
for offline repeat audits. The engine audit verifies actual card construction
and Commander validation. Run engine processes sequentially against the shared DB.

## Verified Name Mappings

On 2026-10-12, the user supplied the original
[Winota list](https://moxfield.com/decks/vreLLzMBwk2e4UoyV7mZUw) and Scryfall
links for its two unresolved names. Scryfall's card records identify
[Jurin, Leading the Charge](https://scryfall.com/card/sld/1240/jurin-leading-the-charge)
with printed name Holga, Relentless Rager, and
[Greymond, Avacyn's Stalwart](https://scryfall.com/card/sld/143/greymond-avacyns-stalwart)
with printed name Rick, Steadfast Leader. Their Oracle IDs and exact printing
API endpoints are pinned in `card_aliases.json`, alongside Unstable Harmonics's
Rhystic Study identity.

Scryfall preflight now passes all four lists with these mappings. Engine audit
with `--aliases docs/primers/card_aliases.json` confirms Jurin, Greymond, and
Rhystic Study load. Winota now loads 99/100 cards (Scuzzback Scrounger missing);
RogSi loads 98/100 (Hexing Squelcher and Samut missing). Yuriko and Kinnan's
previous engine gaps remain. All 11 remaining distinct names have source files
in the current upstream XMage tree. Those files have not been integrated or
tested against the installed MageZero fork; source presence is not proof that
our current runtime supports them.
