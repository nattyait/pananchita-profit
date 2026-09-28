from datetime import date

from app.domain.base_products import deletable_base_products, merge_changes_cogs, merge_refusal
from app.domain.types import ListingMap, SkuCost


def test_base_product_without_listings_is_deletable():
    maps = [ListingMap("TT-2แถม2", "กาแฟ 2แถม2", 4, 0)]
    assert deletable_base_products(["กาแฟ", "กาแฟ 2แถม2"], maps, ["TT-2แถม2"]) == {"กาแฟ"}


def test_mapped_base_product_is_kept_even_if_its_orders_are_cancelled_or_unseen():
    maps = [ListingMap("SKU-ONLY-CANCELLED", "โลชั่น", 1, 0)]
    assert deletable_base_products(["โลชั่น"], maps, []) == frozenset()


def test_name_used_directly_as_product_key_is_kept():
    assert deletable_base_products(["PNC-001"], [], ["PNC-001"]) == frozenset()


MAY, JUN = date(2026, 5, 1), date(2026, 6, 1)


def _c(name, *rows):
    return [SkuCost(name, cost, d) for d, cost in rows]


def test_merge_with_same_cost_history_keeps_cogs():
    assert not merge_changes_cogs(_c("A", (MAY, 11000)), _c("B", (MAY, 11000)))


def test_merge_with_different_cost_changes_cogs():
    assert merge_changes_cogs(_c("A", (MAY, 9700)), _c("B", (MAY, 9600)))


def test_merge_compares_cost_on_every_effective_date_of_either_side():
    assert merge_changes_cogs(_c("A", (MAY, 11000)), _c("B", (MAY, 11000), (JUN, 12000)))


def test_merge_into_a_target_without_cost_keeps_cogs_because_source_costs_move_over():
    assert not merge_changes_cogs(_c("A", (MAY, 11000)), [])


def test_merge_from_a_source_without_cost_changes_nothing_that_was_known():
    assert not merge_changes_cogs([], _c("B", (MAY, 11000)))


def test_merge_refusals():
    names = ["กาแฟ", "กาแฟเก่า", "PNC-001"]
    assert merge_refusal("กาแฟเก่า", "กาแฟ", names, []) is None
    assert merge_refusal("กาแฟ", "กาแฟ", names, []) == "same"
    assert merge_refusal("ไม่มี", "กาแฟ", names, []) == "unknown"
    assert merge_refusal("กาแฟเก่า", "ไม่มี", names, []) == "unknown"
    assert merge_refusal("PNC-001", "กาแฟ", names, ["PNC-001"]) == "used_as_product_key"
