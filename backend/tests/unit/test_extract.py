from app.crawler.extract import extract_page_facts, extract_product_facts

PRODUCT_HTML = """
<html>
<head>
  <title>عطر رجالي صيفي</title>
  <link rel="canonical" href="https://store.example/products/summer-perfume" />
  <meta name="description" content="عطر رجالي مناسب للصيف والدوام" />
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "Product",
    "name": "عطر رجالي صيفي",
    "offers": {
      "@type": "Offer",
      "price": "199.00",
      "priceCurrency": "SAR",
      "availability": "https://schema.org/InStock"
    }
  }
  </script>
</head>
<body>
  <h1>عطر رجالي صيفي للدوام</h1>
  <a href="/products/other-item">منتج آخر</a>
  <a href="https://external.example/other">رابط خارجي</a>
</body>
</html>
"""


def test_extract_page_facts_pulls_title_h1_canonical_and_json_ld():
    facts = extract_page_facts(
        "https://store.example/products/summer-perfume", PRODUCT_HTML, site_hostname="store.example"
    )

    assert facts.title == "عطر رجالي صيفي"
    assert facts.h1 == "عطر رجالي صيفي للدوام"
    assert facts.canonical == "https://store.example/products/summer-perfume"
    assert facts.meta_description == "عطر رجالي مناسب للصيف والدوام"
    assert len(facts.json_ld) == 1
    assert facts.html_hash and facts.content_hash


def test_extract_page_facts_keeps_only_internal_links():
    facts = extract_page_facts(
        "https://store.example/products/summer-perfume", PRODUCT_HTML, site_hostname="store.example"
    )

    assert facts.internal_links == ["https://store.example/products/other-item"]


def test_extract_page_facts_records_headings_images_alt_and_faq():
    html = """
    <html><body><h2>المميزات</h2>
      <img src="/product.webp" alt="صورة المنتج" width="800" height="800" />
      <script type="application/ld+json">{"@type":"FAQPage","mainEntity":[{"name":"كيف يستخدم؟","acceptedAnswer":{"text":"حسب التعليمات."}}]}</script>
    </body></html>
    """

    facts = extract_page_facts("https://store.example/products/item", html, "store.example")

    assert facts.h2 == ["المميزات"]
    assert facts.images == [{"url": "https://store.example/product.webp", "alt": "صورة المنتج", "width": 800, "height": 800}]
    assert facts.faq_items == [{"question": "كيف يستخدم؟", "answer": "حسب التعليمات."}]


def test_extract_product_facts_reads_schema_org_offer():
    facts = extract_page_facts(
        "https://store.example/products/summer-perfume", PRODUCT_HTML, site_hostname="store.example"
    )
    product = extract_product_facts(facts.json_ld)

    assert product == {
        "name": "عطر رجالي صيفي",
        "price": "199.00",
        "original_price": None,
        "currency": "SAR",
        "availability": "https://schema.org/InStock",
        "sku": None,
        "rating": None,
        "review_count": None,
        "image_url": None,
    }


def test_extract_product_facts_returns_none_without_product_type():
    assert extract_product_facts([{"@type": "Organization", "name": "Store"}]) is None


def test_extract_product_facts_reads_sku_rating_and_high_price():
    json_ld = [
        {
            "@type": "Product",
            "name": "ساعة ذكية",
            "sku": "WATCH-001",
            "offers": {"@type": "AggregateOffer", "price": 250, "highPrice": 300, "priceCurrency": "SAR"},
            "aggregateRating": {"@type": "AggregateRating", "ratingValue": "4.5", "reviewCount": "120"},
        }
    ]

    product = extract_product_facts(json_ld)

    assert product["sku"] == "WATCH-001"
    assert product["original_price"] == 300
    assert product["rating"] == 4.5
    assert product["review_count"] == 120


def test_extract_product_facts_rating_defaults_are_honest_none_not_zero():
    """No aggregateRating block at all — must stay None, never fabricated
    as 0 (which would look like a real, terrible rating)."""
    product = extract_product_facts([{"@type": "Product", "name": "منتج بدون تقييم", "offers": {}}])
    assert product["rating"] is None
    assert product["review_count"] is None


def test_extract_product_facts_reads_product_group_schema():
    # Real shape observed from a live Shopify store (ProductGroup for
    # variant-based products) — plain "Product" wasn't enough to catch it.
    json_ld = [
        {
            "@type": "ProductGroup",
            "name": "Men's Wool Runner",
            "offers": {
                "@type": "Offer",
                "price": 110,
                "availability": "https://schema.org/InStock",
                "priceCurrency": "USD",
            },
            "hasVariant": [{"@type": "Product", "url": "https://store.example/products/x?size=8"}],
        }
    ]

    product = extract_product_facts(json_ld)

    assert product == {
        "name": "Men's Wool Runner",
        "price": 110,
        "original_price": None,
        "currency": "USD",
        "availability": "https://schema.org/InStock",
        "sku": None,
        "rating": None,
        "review_count": None,
        "image_url": None,
    }


def test_extract_product_facts_reads_image_from_json_ld():
    json_ld = [
        {
            "@type": "Product",
            "name": "كوب قهوة",
            "image": ["https://cdn.store.example/cup.jpg", "https://cdn.store.example/cup-2.jpg"],
            "offers": {"@type": "Offer", "price": 45, "priceCurrency": "SAR"},
        }
    ]

    product = extract_product_facts(json_ld)

    assert product["image_url"] == "https://cdn.store.example/cup.jpg"


def test_extract_product_facts_ignores_non_http_image_value():
    json_ld = [
        {
            "@type": "Product",
            "name": "كوب قهوة",
            "image": "data:image/png;base64,iVBORw0KGgo=",
            "offers": {"@type": "Offer", "price": 45, "priceCurrency": "SAR"},
        }
    ]

    product = extract_product_facts(json_ld)

    assert product["image_url"] is None
