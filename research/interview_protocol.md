# User study protocol

**New Haven Rent Desk** · 15 minutes per person · run in English

The aim is one number: **how far the app's twelve-month prediction lands from what
a real student actually paid.** Everything else in this protocol exists to make
that number trustworthy and to find out what the app gets wrong.

---

## Who to recruit

International students who moved to New Haven for the 2026–27 academic year and
**signed a lease without viewing the apartment in person**. Four to eight people is
enough to be worth reporting; two is enough to be worth doing.

Second-best: domestic students who moved from out of state. Note which group each
participant is in — their answers will differ and the report should say so.

### Recruiting message

> Hi — I built a small tool for my AI class that works out what a New Haven
> apartment actually costs over a year, including the utilities and lease-timing
> traps that listings don't mention. It's aimed at people who had to pick a place
> before arriving.
>
> Could I borrow 15 minutes? I'd ask about how your own housing search went, then
> run your actual listing through it and get your reaction. Mostly I want to know
> where it's wrong.
>
> No prep needed. If you still have your lease or listing handy that helps, but
> it's fine without.

---

## Before you start

Say this, briefly and in your own words:

> I'll ask about your housing search first, then show you the tool. I'm recording
> numbers, not your name — nothing identifying goes into my report or the public
> repository. Stop me any time. There are no right answers, and the more blunt you
> are about what's wrong with it, the more useful this is.

**Keep part A closed-book.** Do not show the app, do not mention what it computes,
and do not react to their numbers. If you reveal the app's view of utilities first,
every answer after that is anchored and the comparison is worthless.

Open `research/sessions/_template.json`, copy it to `P1.json`, and fill it in as you
go. Write down the numbers while they are talking — not afterwards from memory.

---

## Part A — Their search, before they see anything (8 min)

**A1.** When did you arrive, and when did you start looking for a place?

**A2.** Where did you look? *(Prompt only if they stall: Yale off-campus site,
Facebook groups, KakaoTalk/WeChat groups, Zillow, a friend already here, an agent.)*

**A3.** Roughly how many hours did you spend on the search in total? Think of it as
evenings — how many evenings, how long each?

**A4.** How many places did you seriously consider? Did you see any of them in
person, or on live video, before you signed?

**A5.** What did you end up signing?
- monthly rent
- lease start month, and lease length
- security deposit, in months or dollars
- any broker or application fee

**A6.** Which utilities were included, and which did you pay yourself?

**A7.** **The key question.** Which costs did you only find out about *after* you
moved in? For each one, roughly how much per month?
*(Prompt if they stall: heating, electricity, hot water, internet, laundry,
parking, renters insurance, furniture, snow removal.)*

**A8.** Did you pay rent for any months before you actually arrived in New Haven?
How many, and could you sublet them?

**A9.** Adding it all up — rent plus everything else — what would you say your first
twelve months in that apartment cost in total?
*(If they cannot total it, capture the parts and do the arithmetic yourself later.)*

**A10.** Knowing what you know now, would you have chosen a different place?
What would have changed your mind?

**A11.** What was the single hardest part of the whole process?

---

## Part B — Demo (5 min)

Follow `demo_script.md`. Run **their** listing if they can find it; otherwise pick
the closest match from the snapshot and say out loud that it is a stand-in.

Record what the app predicted, and let them talk while it is on screen. Do not
defend it.

---

## Part C — Their reaction (4 min)

**C1.** Did it show you anything you did not know at the time?

**C2.** Is anything on this screen wrong, for your apartment?

**C3.** If this had existed before you signed, would you have used it? Would you
have trusted the twelve-month number enough to act on it?

**C4.** Would you send it to someone arriving next year? If not, what would have to
change first?

**C5.** What's missing?

**C6.** *(Only if they are enthusiastic.)* Would you be willing to be quoted in my
report, anonymously — something like "a 2026 international student said…"?

---

## What to do immediately afterwards

1. Finish filling in the session JSON while it is fresh.
2. Compute `prediction_error_pct` — the app's twelve-month figure against theirs.
3. Write down one sentence of what surprised *you* in `researcher_note`.

Then run:

```bash
.venv/Scripts/python.exe scripts/build_user_study.py
```

---

## Keeping it anonymous

The repository is public. Session files therefore carry **no names, no exact street
addresses, no contact details, and no landlord names**. Use `P1`, `P2`, … and a
neighbourhood rather than an address. A quote goes in only if the participant said
yes to C6, and only in a form they would be comfortable seeing on the internet.

This is also why the protocol asks for rough figures rather than documents: nobody
needs to hand over a lease to make this measurement useful.

---

## Reading the results honestly

Things that will be tempting and should be resisted:

- **A small sample is a small sample.** Four people is an illustration, not a study.
  Report the individual numbers, not just an average.
- **Recall is not a receipt.** Participants are estimating from memory months later.
  Say so, and prefer ranges over false precision.
- **The people who agree to be interviewed are not a random sample** — they are the
  ones who found the search memorable, which probably means harder than average.
- **A prediction that lands close is not proof the model is right.** It may be right
  for the wrong reasons on one apartment. Report the spread.
- If the app is badly wrong for someone, **that is the most valuable result of the
  whole exercise** and belongs in the report in full.
