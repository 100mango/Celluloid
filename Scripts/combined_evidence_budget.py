"""One fixed allocation for the eleven serial jobs of apple-platforms.yml."""
BUDGETS = {"preflight": 500_000, "mac": 3_000_000, "tv": 2_750_000, "watch": 1_750_000,
           "phone": 2_500_000, "vision": 2_500_000,
           "compact-phone": 1_500_000, "large-phone": 1_500_000,
           "small-ipad": 1_500_000, "large-ipad": 1_500_000, "archive": 500_000}
WHOLE_RUN = 20_000_000
MAX_FILE = 5_000_000
# Every manifest is included; leave 500 KB below the whole-run ceiling.
assert len(BUDGETS) == 11 and sum(BUDGETS.values()) == 19_500_000 < WHOLE_RUN
