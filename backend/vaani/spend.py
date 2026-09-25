"""Spend guard: the check that runs before any paid call is dispatched.

Today this is only a per-process request counter — a stopgap, NOT a cost
ledger. It knows nothing about tokens or money; it just refuses the N+1th
paid request. The real ledger (per-call cost, persisted, per-day limits) is
its own task.

It lives outside providers/ because the limit is our policy, not a vendor's:
every provider must pass through the same check.
"""


class SpendCapExceededError(Exception):
    """Raised BEFORE a paid request is sent, when the cap is already used up.

    Deliberately not a ProviderError: the provider did nothing wrong. Code that
    later fails over from one provider to the next on ProviderError must NOT
    fail over on this — every provider costs money.
    """


class RequestCap:
    """Counts paid requests in this process and refuses past `limit`.

    Create ONE per process and hand it to every provider; the cap only means
    "per process" if everything shares that one instance.
    """

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.used = 0

    def check_and_count(self) -> None:
        """Count one request, or raise if the cap is already reached.

        Check and increment happen with no `await` between them, so on our
        single event loop two concurrent calls cannot both squeeze under the
        cap. A request is counted when dispatched, whether or not it succeeds:
        a failed call can still be billed.
        """
        if self.used >= self.limit:
            raise SpendCapExceededError(
                f"request cap reached: {self.used}/{self.limit} this process"
            )
        self.used += 1
