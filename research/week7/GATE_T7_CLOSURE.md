## 9. Reset Boundary

A live reset was asserted while two valid instructions remained in flight.

Validated properties:

- two instructions were accepted before reset;
- neither pre-reset instruction retired before reset;
- reset invalidated the verification-side B/C/D tags;
- reset functionally invalidated the in-flight pipeline state;
- stale `Curr_Instr` fields were not interpreted as valid pipeline entries;
- no pre-reset instruction retired into the new execution epoch;
- `ExecutionEvent` and retire instruction IDs restarted from 1;
- post-reset accepted and retired counts matched.

Observed live summary:

```text
RESET_BOUNDARY_SUMMARY
pre_reset_accepted=1,2
pre_reset_retired=0
post_reset_accepted=1,2
post_reset_retired=1,2
pipeline_invalidated=1
id_restart=1
status=PASS
