#!/usr/bin/env bash
set -u -o pipefail

cd "$HOME/nckh/risc-v-pipeline"

EXPECTED_HEAD="086e8127101aca9a934bec77af84dc5f87160f09"

ID="week15_final_campaign_attempt_001"

DRIVER="/tmp/${ID}.driver.py"
PLAN="/tmp/${ID}.plan.json"

EXPECTED_DRIVER_SHA="6fea68a005d00210a3582e8320af81e2f2f59b9de1c9f4f4608089f3af7dbc33"
EXPECTED_PLAN_SHA="1274955e6c58db3a27f779d5c02b7e0d15ab0cb8ec654f8d9fffd1d82e2d9ffc"

RUNNER_RC="/tmp/${ID}.runner_rc"
STARTED="/tmp/${ID}.started"
FINISHED="/tmp/${ID}.finished"

{
    echo "campaign=week15_final_campaign_attempt_001"
    echo "authority_head=$EXPECTED_HEAD"
    echo "driver_sha256=$EXPECTED_DRIVER_SHA"
    echo "plan_sha256=$EXPECTED_PLAN_SHA"
    echo "launch_state=STARTED"
} > "${STARTED}.tmp"

mv "${STARTED}.tmp" "$STARTED"

echo "===== WEEK15 FINAL CAMPAIGN ATTEMPT 001 ====="
echo "AUTHORITY_HEAD=$(git rev-parse HEAD)"
echo "BRANCH=$(git branch --show-current)"
echo "WORKTREE_DIRTY_LINES=$(git status --porcelain | wc -l)"
echo "DRIVER_SHA256=$(sha256sum "$DRIVER" | awk '{print $1}')"
echo "PLAN_SHA256=$(sha256sum "$PLAN" | awk '{print $1}')"

rc=0

if test "$(git rev-parse HEAD)" != "$EXPECTED_HEAD"
then
    echo "ERROR=HEAD_MISMATCH"
    rc=97

elif test -n "$(git status --porcelain)"
then
    echo "ERROR=DIRTY_WORKTREE"
    rc=98

elif test "$(
    sha256sum "$DRIVER" |
    awk '{print $1}'
)" != "$EXPECTED_DRIVER_SHA"
then
    echo "ERROR=DRIVER_HASH_MISMATCH"
    rc=95

elif test "$(
    sha256sum "$PLAN" |
    awk '{print $1}'
)" != "$EXPECTED_PLAN_SHA"
then
    echo "ERROR=PLAN_HASH_MISMATCH"
    rc=96

else
    set +e

    python3 "$DRIVER" \
        --plan "$PLAN" \
        --execute

    rc=$?

    set -e
fi

printf '%s\n' "$rc" > "${RUNNER_RC}.tmp"
mv "${RUNNER_RC}.tmp" "$RUNNER_RC"

{
    echo "campaign=week15_final_campaign_attempt_001"
    echo "runner_rc=$rc"
    echo "launch_state=FINISHED"
} > "${FINISHED}.tmp"

mv "${FINISHED}.tmp" "$FINISHED"

echo "FINAL_CAMPAIGN_RUNNER_RC=$rc"
echo "FINAL_CAMPAIGN_DRIVER_FINISHED=YES"

exit "$rc"
