# Working on PaperVoice

Reporting rules for anyone — human or agent — who finishes work in this repo.

## Who reads this

The owner is not a programmer. They judge work by what it lets them do, not by
how it was built. Write for that reader.

## Every wrap-up, in this order

1. **The outcome first.** One sentence saying what is now true for them
   ("the launchers can be double-clicked again", "the repo now explains itself").
2. **How you know.** One or two plain sentences, not a list of commands.
3. **What they must do, if anything.** Steps they have to take, or a choice.
4. **Anything you could not check.** Say it plainly; never bury it.

Keep it short. A longer answer is only justified by real risk, a decision only
they can make, or a technical question they asked.

## Translate, don't dump

Say what a thing means for them, not what it is called:

| Instead of | Write |
| --- | --- |
| commit, push, branch | "saved to GitHub" |
| tag, release, asset | "the download page", "the download link" |
| file permissions, mode bits | "can be double-clicked" |
| virtualenv, dependencies, pip | "the one-time setup" |
| sha256, hash, digest | "an identical copy" |
| endpoint, API, status code | "the app's reply" |
| line counts, commit SHAs, test names | leave them out |

Numbers are worth including when they change what the owner does ("about 300 MB",
"a few minutes"), not as evidence of effort.

## When detail is right

If they ask how something works, or a technical detail changes what they must
do, give it properly and without apology. Otherwise keep it out.

## Honesty over polish

"Not tested on a Mac yet" must sound as direct as "this works". Simpler wording
must never soften a problem or hide a failure. If a check could not run, that is
part of the answer, not a footnote.

## Suggestion chips and next steps

Whenever you offer choices — chips, follow-ups, "what next" — rank them:

1. **Number them and order by importance:** the one that unblocks them first,
   then the ones that remove future annoyance, then the nice-to-haves.
2. **Label each one plainly:** "worth doing now", "optional", "only if it
   bothers you" — never a neutral list of equals.
3. **Say which one you would pick**, in one short clause, and why.
4. **Keep it to three suggestions or fewer** unless they ask for more.
5. **Never frame two options as equal** when one is clearly the sensible next
   step. Make the recommendation obvious and let them decline it.

## Example

Too technical:

> Commit 030970c on main; README 125 lines; SPDX MIT detected; modes 100755;
> working tree clean.

Right:

> The repo now explains itself to a visitor and shows an MIT licence, so it looks
> like a normal project if you share the link. Nothing for you to do.
> I checked the live files; I did not view the rendered page in a browser.
