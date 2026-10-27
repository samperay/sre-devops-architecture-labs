# sre-devops-architecture-labs

Hands-on labs for an experienced SRE/Automation Engineer moving toward an SRE/DevOps Architect role. The repository holds working systems, the failures found in them, and the design decisions that follow. It is not a theory handbook.

## Learning methodology

Each project follows the same loop:

**BUILD → UNDERSTAND → BREAK → FIX → DESIGN**

1. **BUILD** — implement the smallest system that meets the current milestone.
2. **UNDERSTAND** — explain the components, data flow, and operating limits in your own words.
3. **BREAK** — force realistic failures (crash, delay, duplicate, overload, bad input).
4. **FIX** — restore correct behavior and record what changed.
5. **DESIGN** — state the trade-off and the next design decision before writing more code.

A later milestone starts only after the current one has been reviewed and merged.

## How projects are organized

| Path | Role |
| --- | --- |
| `ROADMAP.md` | The 10 planned projects: problem, deliverable, competencies, milestones, interview relevance. |
| `PROGRESS.md` | Current learning state. Updated only when there is evidence. |
| `projects/NN-name/` | One directory per project, added when that project starts. |
| `.github/pull_request_template.md` | Required sections for every implementation PR. |

Project directories are created one at a time. Only `projects/01-async-task-processor/` exists today. Later projects stay in the roadmap until implementation begins.

## Pull requests as milestones

A GitHub pull request is how a milestone is finished. Open it against `master` from a feature branch. The PR describes the problem, the design change, how it was tested, and what was learned.

A milestone counts as implementation-complete only after the PR is reviewed, the tests in the PR have been run, and the PR is merged into `master`.

## Architectural readiness is more than a merge

A merged PR shows that a slice of the system builds and was accepted. It does not show that you can explain the design, operate it, or choose the next trade-off.

`PROGRESS.md` tracks implementation, understanding, and architecture readiness separately. Architecture readiness needs demonstrated design reasoning, troubleshooting, operational understanding, and communication. Those stay at `NOT STARTED` until there is evidence for them.
