# Gate T8 Closure — Functional Scoreboard + Performance Monitor

## 1. Gate Status

**Gate T8: PASS**

Branch:

`research/week8-scoreboard-performance`

Week 8 extends the frozen Week-5, Week-6, and Week-7 verification baseline without modifying the DUT or frozen verification artifacts.

---

## 2. Verification Objective

Week 8 separates architectural correctness from timing/performance correctness.

For instruction \(i\):

$$
F_i \in \{\mathrm{PASS},\mathrm{FAIL}\}
$$

$$
P_i \in \{\mathrm{PASS},\mathrm{FAIL}\}
$$

The two verdicts are intentionally independent.

A correct architectural result does not imply correct timing, and correct timing does not imply a correct architectural result.

---

## 3. Functional Scoreboard

The Functional Scoreboard checks WHAT an instruction commits.

Checked properties include:

* architectural register-write enable;
* destination register;
* writeback data;
* store enable;
* store address;
* store data;
* architectural x0 invariant.

Functional expectations are derived from the independent Golden Functional Model and Week-6 `ExpectedRetire` objects.

Retirement cycle is deliberately excluded from the functional verdict.

Therefore, an incorrect architectural writeback value causes:

`Functional FAIL`

independent of whether the instruction retired at the expected cycle.

Store observations are associated with the frozen DUT C-stage physical memory side-effect point and correlated with the same `instruction_id` at logical D-stage retirement.

Golden architectural memory addresses are never silently truncated to the DUT 9-bit memory address interface.

---

## 4. Performance Monitor

The Performance Monitor checks WHEN an instruction retires.

For instruction \(i\):

$$
\Delta_i =
C^{obs}_{retire,i}
-
C^{exp}_{retire,i}
$$

Classification:

$$
\Delta_i=0
\Rightarrow
\mathrm{Performance\ PASS}
$$

$$
\Delta_i>0
\Rightarrow
\mathrm{late\ retirement/excess\ latency}
$$

$$
\Delta_i<0
\Rightarrow
\mathrm{early\ retirement/timing\ error}
$$

The performance verdict uses only:

* `instruction_id`;
* expected retire cycle from Timing Oracle v1;
* observed retire cycle from Retire Monitor.

Functional values such as `regwrite`, `rd`, `wdata`, store state, and x0 do not affect the performance verdict.

Metrics include:

* checked instruction count;
* performance failure count;
* late count;
* early count;
* total excess cycles;
* maximum excess cycles;
* missing instruction IDs.

---

## 5. Cross-Verdict Classification

Week 8 defines four independent classifications:

| Functional | Performance | Classification                    |
| ---------- | ----------- | --------------------------------- |
| PASS       | PASS        | `CORRECT_ON_TIME`                 |
| FAIL       | PASS        | `FUNCTIONAL_ONLY_FAIL`            |
| PASS       | FAIL        | `PERFORMANCE_ONLY_FAIL`           |
| FAIL       | FAIL        | `FUNCTIONAL_AND_PERFORMANCE_FAIL` |

All four logical quadrants are exercised by Week-8 unit-level integration tests.

The classifier does not recompute functional or performance correctness. It combines the independently produced results using `instruction_id`.

---

## 6. Live RTL Evidence

### T01 — Correct and on time

Both executed instructions were classified:

`CORRECT_ON_TIME`

Observed summary:

```text
instructions=2
functional_failures=0
performance_failures=0
excess_cycles=0
status=PASS
```

Therefore:

$$
F=\mathrm{PASS},\qquad P=\mathrm{PASS}
$$

### T11 — Functional-only failure

The first instruction was `CORRECT_ON_TIME`.

The dependent instruction was observed as:

```text
classification=FUNCTIONAL_ONLY_FAIL
functional_pass=0
performance_pass=1
delta=0
functional_failed=write_data
```

Summary:

```text
instructions=2
functional_failures=1
performance_failures=0
excess_cycles=0
status=PASS
```

Therefore:

$$
F=\mathrm{FAIL},\qquad P=\mathrm{PASS}
$$

The failure is architectural/writeback-related rather than timing-related.

### T19 — False load-to-x0 stall

The consumer was observed as:

```text
classification=PERFORMANCE_ONLY_FAIL
functional_pass=1
performance_pass=0
delta=1
functional_failed=none
```

Summary:

```text
instructions=2
functional_failures=0
performance_failures=1
excess_cycles=1
status=PASS
```

Therefore:

$$
F=\mathrm{PASS},\qquad P=\mathrm{FAIL}
$$

The DUT produces the correct architectural result but retires the consumer one cycle later than expected.

### T20 — False unused-rs2 load-use stall

The consumer was observed as:

```text
classification=PERFORMANCE_ONLY_FAIL
functional_pass=1
performance_pass=0
delta=1
functional_failed=none
```

Summary:

```text
instructions=2
functional_failures=0
performance_failures=1
excess_cycles=1
status=PASS
```

Again:

$$
F=\mathrm{PASS},\qquad P=\mathrm{FAIL}
$$

This demonstrates that an unnecessary stall is a performance defect even when architectural state remains correct.

---

## 7. Experimental Interpretation

The live results demonstrate that functional and performance correctness cannot be collapsed into a single verdict.

In particular:

$$
\mathrm{correct\ architectural\ state}
\not\Rightarrow
\mathrm{correct\ timing}
$$

as demonstrated by T19 and T20.

Conversely:

$$
\mathrm{correct\ timing}
\not\Rightarrow
\mathrm{correct\ architectural\ state}
$$

as demonstrated by T11.

This separation prevents unnecessary stalls from being misclassified as functional failures and prevents correct timing from masking incorrect architectural data.

---

## 8. Known DUT Defects

The frozen known DUT defects remain:

* H11
* H13
* H18
* H19
* H20

Week 8 improves failure attribution without modifying these frozen baseline observations.

The Week-8 live evidence specifically establishes:

* H11: functional/writeback defect;
* H19: performance-only defect in the observed execution;
* H20: performance-only defect in the observed execution.

No known defect is reinterpreted as missing stimulus.

---

## 9. Complexity

Expected values are indexed by `instruction_id` using Python dictionaries.

For ordinary Python dictionary operation, expected-value lookup is **average-case** constant time:

$
T_F=O(1)
$

for the Functional Scoreboard and:

$
T_P=O(1)
$

for the Performance Monitor per retired instruction.

Therefore, online checking over \(N\) retired instructions is:

$
T_{online}(N)=O(N)
$

on average.

Stored expectation and result logs require:

$
S(N)=O(N)
$

Some final reporting operations sort instruction IDs (for example, missing-ID reporting), so those reporting paths may require:

$
T_{report}(N)=O(N\log N)
$

This does not change the per-retirement online-checking cost.

Verification-side pipeline identity tracking remains bounded by the fixed pipeline depth.

---

## 10. Final Regression

Final Python regression:

```text
Week 8: 36 passed
Week 7: 40 passed
Week 6: 64 passed
Week 5: 142 passed
```

The frozen DUT and Week-5/6/7 verification baselines remain unchanged.

---

## 11. Gate T8 Decision

Gate T8 requirements are satisfied:

* Functional Scoreboard implemented;
* wrong architectural `wdata` produces Functional FAIL;
* Performance Monitor implemented;
* expected and observed retire timing are compared independently;
* excess/unnecessary latency is detected;
* Functional and Performance verdicts are independent;
* all four logical cross-verdict quadrants are unit-tested;
* live `CORRECT_ON_TIME` demonstrated by T01;
* live `FUNCTIONAL_ONLY_FAIL` demonstrated by T11;
* live `PERFORMANCE_ONLY_FAIL` demonstrated by T19 and T20;
* unnecessary stalls can produce Functional PASS and Performance FAIL;
* correct timing can coexist with an architectural Functional FAIL;
* no frozen DUT or Week-5/6/7 artifact was modified;
* no unexplained Week-8 timing mismatch remains.

**Gate T8: PASS / CLOSED.**
