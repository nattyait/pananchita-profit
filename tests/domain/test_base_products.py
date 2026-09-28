from app.domain.base_products import deletable_base_products
from app.domain.types import ListingMap


def test_base_product_without_listings_is_deletable():
    maps = [ListingMap("TT-2แถม2", "กาแฟ 2แถม2", 4, 0)]
    assert deletable_base_products(["กาแฟ", "กาแฟ 2แถม2"], maps, ["TT-2แถม2"]) == {"กาแฟ"}


def test_mapped_base_product_is_kept_even_if_its_orders_are_cancelled_or_unseen():
    maps = [ListingMap("SKU-ONLY-CANCELLED", "โลชั่น", 1, 0)]
    assert deletable_base_products(["โลชั่น"], maps, []) == frozenset()


def test_name_used_directly_as_product_key_is_kept():
    assert deletable_base_products(["PNC-001"], [], ["PNC-001"]) == frozenset()
