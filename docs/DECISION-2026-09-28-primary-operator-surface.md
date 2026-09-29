# Decision: NeuraJL is NIRA's primary operator surface (2026-09-28, Matt)

NeuraJL is promoted to the primary operator surface of NIRA, and it is Harpe's operator kernel.

## What the evidence supports

NeuraJL provides long-horizon behaviour that has been demonstrated directly:
- truthful revival after kernel death;
- persistent structured state;
- bounded authority beneath the language (an OS-level fence);
- process and job awareness;
- reorientation across compaction;
- disposable, isolated machinery;
- Julia-native typed state.

The long runs back this up:
- tin1 ran 10.0 h, and 99.8% of the ports it attempted passed.
- tin2 and tin3 were cut short by provider limits, not by NeuraJL. In both, every completed task graded correct. tin3 held through 255 compactions and a kernel kill.

Whether NeuraJL is better than a steelmanned IPython **has not been measured**, and this decision does not claim it.

## IPython

IPython is set aside as the operator surface of the conventional Python stack. It is not treated as an adversary until Matt funds the head-to-head, on a budget of $40–50, as the grittiest long-horizon test possible.

## Consequences

- New operator work targets NeuraJL.
- The next long run is endurance, not comparison.
- The harness work continues: pacing, the context size, and p3 as a task long enough to tell settings apart.
