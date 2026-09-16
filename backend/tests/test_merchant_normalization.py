import uuid

from app.models.merchant import Merchant, MerchantAlias
from app.services.merchant_normalization import normalize_merchant_key, resolve_merchant


def _eval_clause(clause, obj) -> bool:
    clauses = getattr(clause, "clauses", None)
    if clauses is not None:
        return all(_eval_clause(c, obj) for c in clauses)
    attr = clause.left.key
    return getattr(obj, attr) == clause.right.value


class FakeSession:
    """Same convention as test_categories.py's FakeSession, extended to cover two
    related tables (merchants + merchant_aliases)."""

    def __init__(self, merchants=None, aliases=None) -> None:
        self.merchants: dict[uuid.UUID, Merchant] = {m.id: m for m in (merchants or [])}
        self.aliases: dict[uuid.UUID, MerchantAlias] = {a.id: a for a in (aliases or [])}

    def _store_for(self, model):
        return self.merchants if model is Merchant else self.aliases

    def get(self, model, pk):
        return self._store_for(model).get(pk)

    def add(self, obj) -> None:
        self._store_for(type(obj))[obj.id] = obj

    def commit(self) -> None:
        pass

    def scalars(self, stmt):
        entity = stmt.column_descriptions[0]["entity"]
        where = stmt.whereclause
        return [o for o in self._store_for(entity).values() if where is None or _eval_clause(where, o)]

    def scalar(self, stmt):
        rows = self.scalars(stmt)
        return rows[0] if rows else None


STARBUCKS_VARIANTS = [
    "STARBUCKS #18273 AUSTIN TX",
    "STARBUCKS STORE 18273",
    "SQ *STARBUCKS",
    "STARBUCKS 01827",
]

AMAZON_VARIANTS = [
    "AMZN MKTP US*2X82",
    "AMAZON.COM*123",
    "AMZN.COM/BILL",
    "Amazon Marketplace",
]


def test_normalize_merchant_key_starbucks_variants_converge() -> None:
    assert {normalize_merchant_key(v) for v in STARBUCKS_VARIANTS} == {"STARBUCKS"}


def test_normalize_merchant_key_amazon_variants_do_not_converge_at_tier_one() -> None:
    # Tier 1 alone is not expected to unify these; that's the seed-dictionary tier's job.
    assert normalize_merchant_key("AMAZON.COM*123") == "AMAZON"
    assert normalize_merchant_key("AMZN.COM/BILL") == "AMZN"
    assert normalize_merchant_key("AMZN MKTP US*2X82") == "AMZN MKTP US"
    assert normalize_merchant_key("Amazon Marketplace") == "AMAZON MARKETPLACE"


def test_resolve_merchant_starbucks_variants_converge_on_one_merchant() -> None:
    session = FakeSession()
    merchant_ids = {resolve_merchant(session, v).id for v in STARBUCKS_VARIANTS}
    assert len(merchant_ids) == 1
    assert list(session.merchants.values())[0].name == "Starbucks"
    assert len(session.aliases) == 1  # all four share one normalized key


def test_resolve_merchant_amazon_variants_converge_on_one_merchant() -> None:
    session = FakeSession()
    merchant_ids = {resolve_merchant(session, v).id for v in AMAZON_VARIANTS}
    assert len(merchant_ids) == 1
    assert list(session.merchants.values())[0].name == "Amazon"
    assert len(session.aliases) == 4  # four distinct normalized keys, one merchant


def test_resolve_merchant_repeat_call_does_not_duplicate_rows() -> None:
    session = FakeSession()
    first = resolve_merchant(session, "STARBUCKS #18273 AUSTIN TX")
    second = resolve_merchant(session, "STARBUCKS #18273 AUSTIN TX")
    assert first.id == second.id
    assert len(session.merchants) == 1
    assert len(session.aliases) == 1


def test_resolve_merchant_unknown_description_auto_creates() -> None:
    session = FakeSession()
    merchant = resolve_merchant(session, "JOES PIZZA #4521 CHICAGO IL")
    assert merchant.name == "Joes Pizza"
    assert len(session.merchants) == 1
    assert len(session.aliases) == 1
    assert list(session.aliases.values())[0].alias == "JOES PIZZA"
