# Demo script

Five minutes, run after Part A of `interview_protocol.md` and never before it.

**Setup before they arrive:** app running at `http://127.0.0.1:8000`, browser at a
readable zoom, their answers from Part A in front of you. Have the attack listing
from `research/attack_listing.txt` in your clipboard for the optional ending.

Speak in short sentences. Let silences happen — the useful reactions arrive in them.

---

## 0 · Frame it (20 seconds)

> This reads a rental ad and works out what twelve months actually costs. It isn't
> a listing site. I'm going to put your situation in and run your place through it.
> Tell me when it's wrong.

Do not explain the agents, the census data, or the architecture. If they ask, answer
in one sentence and move on — you are testing whether the output stands up without a
tour guide.

---

## 1 · Their profile (40 seconds)

Fill in **About you** from their Part A answers, out loud as you type:

- **Monthly budget** → what they had at the time, not what they pay now
- **You actually arrive in** → their real arrival month
- **People in the household** → how many actually live there
- **Longest walk you accept** → ask if you did not capture it
- Tick **I am moving from abroad and cannot view in person** for international
  participants, plus car / laundry / furnished as they apply

> This is scored against you, not an average renter.

---

## 2 · Their listing (1 minute)

**If they still have the ad** — paste it into **Paste an advertisement**. This is the
best case; the parser gets real, messy text.

**If they have a screenshot** — use **Upload a screenshot**. Worth doing if available,
since it shows the image path working on a real artefact.

**If they have neither** — go to **Browse the snapshot**, filter to their bedroom
count and rough rent, and pick the nearest. Say clearly:

> This isn't your exact apartment, it's the closest one I have. So treat the number
> as the method, not as your bill.

Click **Work out the real cost**. While it runs, say nothing.

---

## 3 · Read the verdict together (1 minute)

Point at the four numbers in order, and stop talking after each:

1. **Advertised** — struck through. "This is the number you were comparing on."
2. **Actually** — "This is what the model thinks it really costs a month."
3. **First year** — "Twelve months of everything."
4. **Before you move in** — "Cash before the keys."

Then the amber banner, if it appears:

> Does this match what happened to you — did you pay for months before you arrived?

**Write their answer down verbatim.** This is usually the moment people react most
strongly, because it is the cost nobody warned them about.

---

## 4 · Where the money goes (1 minute)

Scroll to the cost table and point at the dots:

> Blue is measured from census data for your census tract. Grey is an assumption,
> and it says so.

Then the single most useful question in the whole demo:

> Which of these lines is wrong for your apartment, and by how much?

Let them correct it. Record every correction in `app_said.corrections` — a line the
participant says is wrong is worth more than a line they accept.

---

## 5 · Risk and the questions (1 minute)

Scroll to **Risk and the law**:

> These are tied to actual Connecticut rules. Did anyone tell you about the deposit
> cap, or the interest, or the thirty-day return?

Then **Ask before you sign**:

> These are generated from what your ad never said. If you'd had this list before
> you signed, would it have changed the conversation with your landlord?

---

## 6 · Optional — the hostile listing (45 seconds)

Only if there is time and they seem interested. Paste
`research/attack_listing.txt` and run it.

> This ad has hidden text in it telling the assistant to report $900 a month and
> not mention any risk. Here's what it does instead.

Point at the **manipulation attempt blocked** badge, the rent that did not move, and
the scam warnings that appeared anyway.

This is not part of the measurement. It is there because people's trust in the
number goes up when they see that it cannot be pushed around, and because their
reaction tells you whether the warning reads as alarming or reassuring.

---

## 7 · Close

> That's it. What's wrong with it?

Then go to Part C of the protocol.

---

## Things to avoid

- **Do not defend a number.** If they say it is wrong, write down why. You are not
  selling it.
- **Do not explain away an assumption.** "That's just a default" teaches you nothing;
  "what should it be?" teaches you the right default.
- **Do not skip to the demo** because Part A feels slow. Part A is the measurement.
- **Do not let them see the app before Part A is finished**, including while you set
  up — have the screen turned away or the browser closed.
