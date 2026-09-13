# Running the pilot

One lab member uses this for real work while you watch and say nothing. It is
the only test that has not been run: everything up to now was checked by the
people who built it, and that is not a test.

Ninety minutes, including the conversation afterwards.

---

## Before the session

- **Pick someone who has not used it.** A fellow or a student who will actually
  analyze these recordings. Not somebody who watched you build it.
- **Have a subject that genuinely needs QC review.** The demo works for the
  walkthrough, but the second half should be a real subject, because a real one
  has flags worth arguing about.
- **Check the app runs and a worker is up.** The Status screen should say one
  worker, heard from seconds ago. A pilot derailed by a stopped worker tells you
  nothing about the interface.
- **Have `docs/install.md` open on their machine, not yours.** If they need
  something that is not written down, that is a finding.

Set expectations out loud, once:

> I am going to sit here and not help. If you get stuck, that is the most useful
> thing that can happen, so keep going as long as you can stand it, and think out
> loud if you can.

## What they do

Four tasks, in this order. Do not read the steps aloud; give them the task and
let them find it.

1. **The ten-minute walkthrough alone.** From `docs/install.md`: build the demo,
   start the app, look at the demo subject, and find what the QC screen says
   about it.
2. **Review a real subject and sign it.** Decide every flag, changing the action
   where the proposal is wrong, and sign. This is the task most likely to
   surface something, because it is the one that requires judgment rather than
   clicking.
3. **Run two analyses of their choosing**, with parameters they picked, on the
   subject they just signed. `bandpower_contrast` and `tfr_onset` are the guide's
   suggestion, but let them choose: what they reach for is data.
4. **Export a bundle from one result** and tell you, from the bundle alone, what
   was run and whether they would trust it.

## What to write down

Everything, without helping. Specifically:

- **Every hesitation.** Where they stopped to read, re-read, or scrolled back.
- **Every wrong click**, and what they expected it to do.
- **Every question they ask you.** Write the question down and say you will
  answer afterwards.
- **Every word they use** that the interface does not. If they say "channel" and
  it says "derivation", that is the interface's problem.
- **Where they were confident and wrong.** The most expensive finding available:
  they did something incorrect and did not notice.

Do not write down what you would have done differently. That is not what this is
measuring.

## Afterwards

Ask three questions, in this order, and let them answer before you speak:

1. What did you think this was doing at the point you got stuck?
2. Was there anything you were not sure you were allowed to do?
3. If you had to run this again tomorrow without me, what would you look up?

Then, and only then, answer the questions they parked.

## Triage

Every observation goes into `docs/backlog.md` tagged one of three ways:

- **blocker** they could not proceed, or they proceeded and got something wrong.
- **friction** they got there, slower or more anxiously than they should have.
- **idea** a thing they wanted that does not exist.

With a one-line proposed fix and a size, S, M or L.

Then separate three things that look alike and are not:

- **The app is wrong.** Fix it.
- **The documentation is wrong.** Fix that.
- **The user is new.** Fix nothing. Being unfamiliar is not a defect, and
  changing the software every time somebody is new is how an interface becomes a
  pile of special cases.

Blockers get planned and fixed before the second session. Friction items sized S
get batched into one change. Ideas are left alone, on purpose.

## The second session

Same person, same tasks, a few weeks later. It goes smoothly or it does not, and
if it does not the first round of fixes addressed the wrong thing.

That is the point at which `v1.0.0` gets tagged, and not before.
