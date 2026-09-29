"""
Frozen Week-13 Adaptive-CGS configuration selected from the
81-run pilot campaign.

Pilot evidence:
  harness revision:
    f8951de7d4c1ddd25adf7c6534e6791a7661613a

Selection rule:
  1. median normalized L2-Intent AUC;
  2. median L2-Intent bins at N=10000;
  3. ties: lower median wallclock, larger batch,
     smaller epsilon, smaller alpha.
"""

SELECTED_EPSILON = 0.10
SELECTED_ALPHA = 0.5
SELECTED_Q_FLOOR = 0.05
SELECTED_NOMINAL_BATCH = 500

PILOT_HARNESS_REVISION = (
    "f8951de7d4c1ddd25adf7c6534e6791a7661613a"
)

PILOT_RUN_COUNT = 81
PILOT_CONFIGURATION_COUNT = 27
PILOT_SEEDS = (
    13001,
    13002,
    13003,
)
