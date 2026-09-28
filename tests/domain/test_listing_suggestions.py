import pytest

from app.domain.listing_suggestions import (
    ListingMapSuggestion,
    guess_units,
    parse_bulk_rows,
    suggest_listing_maps,
    title_core,
)
from app.domain.types import ListingMap


@pytest.mark.parametrize("title, core", [
    ("[โปร3แถม2 มีจำนวนจำกัด] เอสชัวร์ โปร คอฟฟี่ กาแฟปรุงสำเร็จรูป", "เอสชัวร์ โปร คอฟฟี่ กาแฟปรุงสำเร็จรูป"),
    ("G.(โปรรวม) AM Wow น้ำยาเอนกประสงค์", "AM Wow น้ำยาเอนกประสงค์"),
    ("[ 2 ถุง ] AM Wow  น้ำยาเอนกประสงค์", "AM Wow น้ำยาเอนกประสงค์"),
    ("[โปรพิเศษ3แถม2]บายคาบูเอ็กซ์ Bye-kabu X", "บายคาบูเอ็กซ์ Bye-kabu X"),
    ("ัLOVE STORY BODY LOTION", "LOVE STORY BODY LOTION"),  # stray leading vowel mark in the shop's title
    ("S sure cocoa แบรนด์ ปนันชิตา", "S sure cocoa แบรนด์ ปนันชิตา"),
])
def test_title_core_drops_leading_promo_tags(title, core):
    assert title_core(title) == core


@pytest.mark.parametrize("title, variant, units", [
    ("x", "3แถม2", 5),
    ("x", "2 แถม 1", 3),
    ("x", "แดง2 แถม 2", 4),
    ("x", "12แถม4", 16),
    ("x", "เขียว2+แดง2", 4),
    ("x", "มะม่วง1+แอปเปิ้ล1+เมล่อน1", 3),
    ("x", "กลิ่นเเปปเปอร์มินต์ 1ลัง 6ถุง", 6),
    ("x", "รีดูโคส1กล่อง", 1),
    ("x", "ชาไทย 3", 3),
    ("x", "kiss Love1", 1),
    ("[โปร3แถม2 มีจำนวนจำกัด] เอสชัวร์ โปร คอฟฟี่", "", 5),
    ("[โปร3กล่องไม่มีแถม] เอสชัวร์ โปร คอฟฟี่", "", 3),
    ("[1 กล่อง] CALCIUM PLUS", "", 1),
    ("[โปร3แถม1] รีดูโคสอีจี 1 กล่องมี 10 แคปซูล", "รีดูโคส1กล่อง", 1),  # variation wins over title
    ("LOVE STORY BODY LOTION", "โลชั่นรวม3กลิ่น", None),  # 3 scents, not 3 tubes → no guess
    ("เพอเบอร์รี่บุก บรรจุ 7 ซอง", "", None),  # sachets per pack are not sold units
])
def test_guess_units_from_promo_text(title, variant, units):
    assert guess_units(title, variant) == units


def test_suggests_base_product_of_the_same_listing_under_an_older_promo_title():
    unmapped = [
        ("K1", "[โปร3แถม2 มีจำนวนจำกัด] เอสชัวร์ โปร คอฟฟี่", ""),
        ("K2", "S sure cocoa แบรนด์ ปนันชิตา", "3กล่อง"),
    ]
    mapped = [("[โปร2แถม2] เอสชัวร์ โปร คอฟฟี่", "กาแฟเอสชัวร์"), ("[โปร2แถม2] เอสชัวร์ โปร คอฟฟี่", "กาแฟเอสชัวร์"),
              ("เอสชัวร์ โปร คอฟฟี่", "กาแฟเก่า")]
    assert suggest_listing_maps(unmapped, mapped) == {
        "K1": ListingMapSuggestion("K1", "กาแฟเอสชัวร์", 5),  # most common base among matching titles
        "K2": ListingMapSuggestion("K2", "", 3),  # new product: units guessed, base left for staff
    }


def test_bulk_rows_keep_only_rows_with_base_product_and_positive_units():
    rows = [("A", " กาแฟ ", "5"), ("B", "", "3"), ("C", "โลชั่น", ""), ("D", "โลชั่น", "0"), ("E", "โลชั่น", "x")]
    maps, invalid = parse_bulk_rows(rows)
    assert maps == (ListingMap("A", "กาแฟ", 5),)
    assert invalid == 3  # C, D, E have a base product but no usable units; B is simply left for later
