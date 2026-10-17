# Measuring Exam Readiness Without Fooling Yourself

> Practice scores go up for reasons that have nothing to do with being ready: you have seen the questions before, a guess happened to be right, or you felt surer than you should. In my Oracle 1Z0-071 study app I tried to measure readiness in a way repetition cannot inflate. Here is the design and the math behind it, in plain terms.

## Three ways a practice score lies

**Repetition.** The first version of my app had 79 questions and a 63-question mock exam. Each new mock repeated about 80% of the previous one, so scores could rise from memory, not skill.

**Lucky guesses.** On a four-option question, a pure guess is right a quarter of the time. If a correct answer clears the question from your mistakes list, a guess can hide a real gap for good.

**Overconfidence.** Being right while unsure and wrong while sure are both important signals. A plain percentage records neither.

The app now has 453 questions, and the design below keeps those three effects out of its numbers.

## Confidence on every answer

When you check a practice answer, you also rate it: Sure, Think so or Guessing (keys S, T and G). Mock exams have the same rating as an option. The Progress page then shows calibration: for each rating, how often you were actually right. The target for "Sure" is 90% or more. If your "Sure" answers are right 70% of the time, you are not noticing what you do not know.

## Mistakes need proof to clear

A question counts as a mistake when you answer it wrongly, or when you answer it correctly but rated the answer as a guess. It stays on the list until you answer it correctly, rated Sure or Think so, on two different days. Answering it right twice in five minutes does not count, because that is short-term memory.

Confident wrong answers come first in the list, then other wrong answers, then lucky guesses.

## Spacing with SM-2

Questions and flashcards are scheduled with SM-2. Each review gets a quality from 0 to 5; for questions it comes from the confidence rating:

| Answer | Quality |
|---|---|
| Correct, Sure | 5 |
| Correct, Think so | 4 |
| Correct, Guessing | 2 (counts as a lapse) |
| Wrong | 1 |
| Wrong, Sure | 0 |

A quality of 3 or more extends the interval: 1 day, then 3 days, then the previous interval times an "ease" factor that starts at 2.5. Anything below 3 resets the item, so it is due again right away, and lowers its ease. With three Sure answers the intervals are 1, 3 and 8.1 days. With three Think so answers the third interval is 7.5 days. One confident miss after two Sure answers drops the ease from 2.7 to 1.9, so that question comes back sooner and grows its intervals more slowly from then on.

## Mastery per objective

Every question, flashcard and lab belongs to one of the exam's 60 objectives. For each objective the app keeps two totals: evidence for "you know this" (alpha) and evidence against it (beta). The estimate is the mean of a Beta distribution that starts at Beta(1, 1), which means "no idea yet, every accuracy equally likely":

    estimate = (alpha + 1) / (alpha + beta + 2)

Evidence is weighted. A correct Sure answer adds 1.0 to alpha, a correct Think so adds 0.8, and a correct guess adds 0.5 to each side. A wrong answer adds 1.0 to beta, or 1.5 if you were sure. A passed lab adds 2.0, and each failed try adds 0.5 to beta, up to three tries. Flashcards add smaller amounts. All evidence fades with a 30-day half-life: two months old counts a quarter.

The levels are deliberately coarse: Not started (under 2 units of evidence), Weak (estimate under 60%), Learning (under 80%) and Strong. For example, five confident correct answers and one confident miss give alpha 5 and beta 1.5, so the estimate is 6 / 8.5, about 71%: Learning, not Strong.

## Readiness from first answers only

Mastery uses every answer, which is right for deciding what to study but wrong for predicting a score: the exam asks questions you have never seen. So readiness uses only the first answer you ever gave to each question.

A first answer in a mock counts fully, one in untimed practice counts 0.6. Both fade with the same 30-day half-life. Below 15 units of evidence, the app says there is not enough evidence instead of showing a number.

The totals become a Beta distribution over your accuracy, as above. The app then asks what a 63-question exam score would look like, given that the accuracy itself is uncertain. That is a beta-binomial distribution: for every possible score from 0 to 63, the probability of getting it. A pass needs 63%, which is 40 correct answers out of 63. The pass probability is the total probability of 40 or more. The score range shown is the 10th to 90th percentile.

## A worked example

I ran the engine's `readiness` function on synthetic progress states, all answered "today" so the half-life plays no part.

**Scenario A: 40 questions, first answered in practice, 30 of them correct.** Each first answer weighs 0.6, so alpha = 30 × 0.6 = 18 and beta = 10 × 0.6 = 6, a total of 24 units of evidence. The accuracy estimate is Beta(19, 7), with mean 19 / 26, about 73%. Over 63 questions, the beta-binomial gives:

- pass probability: 0.84
- score range: 59% to 86% (37 to 54 correct)

**Scenario B: the same 40 questions, then each answered correctly five more times, rated Sure.** That is 240 answers with 230 correct. A plain practice score would say 96%. Readiness still says 0.84 and 59% to 86%, because only the first answers count.

**Scenario C: only 20 first answers, 15 correct.** That is 12 units of evidence, under the minimum of 15, so the app shows no estimate.

**Scenario D: one full mock, 44 of 63 correct.** Mock answers count fully, so there are 63 units of evidence. The estimate is about 69%, the pass probability 0.79 and the range 59% to 79%. The same mock taken 30 days ago counts half: 31.5 units, pass probability 0.74 and a wider range of 56% to 81%.

A's expected score is higher, but D's range is narrower because it rests on more evidence. When deciding whether to book, the low end matters more than the middle.

## Mock exams that do not repeat themselves

A mock has 63 questions and 120 minutes and gives no feedback until it ends. It takes one question from each official objective first, since Oracle publishes no section weights. Questions are chosen freshest first: never seen anywhere, then seen only in practice, then those from the oldest mock.

Once you have answered most of the bank, some repetition is unavoidable, so every report states how many questions were new to you and your score on those. If that fresh score drifts below the overall one, memory is carrying the result.

## What changing your answer tells you

During a mock the app records every answer you select. The report compares your first and final answer on each question and sorts changes into right to wrong, wrong to right, and wrong to wrong, each linked to the question. If most changes go from right to wrong, trust your first instinct more.

The report also shows scores per section and per confidence rating, single- versus multi-answer accuracy, and the slowest questions. Unanswered questions score zero in the report but are not saved as answers, so an unfinished mock does not flood the mistakes list or pull readiness down.

## What I would do next

- **Misconception tracking.** Tag the wrong options of all 453 questions with the misconception each one represents, so the app can say "you keep confusing WHERE and HAVING" rather than "objective 6.3 is weak".
- **Topic weighting**, if Oracle ever publishes section weights. Until then, question counts per topic stay even.

The dashboard, the printable readiness report and the evidence-based badges described in earlier
drafts of this list are now built. The badges all have checkable conditions, for example three full
mocks at 80% or more on questions new to you, at least three days apart.
