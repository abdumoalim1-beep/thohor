from app.crawler.platform_detection import detect_platform_from_html, detect_platform_from_pages


def test_detects_shopify_from_cdn_marker():
    html = '<html><head><link href="https://cdn.shopify.com/s/files/1/theme.css"></head><body></body></html>'
    assert detect_platform_from_html(html) == "shopify"


def test_detects_salla_from_config_marker():
    html = "<html><body><script>Salla.config.init({});</script></body></html>"
    assert detect_platform_from_html(html) == "salla"


def test_detects_zid_from_cdn_marker():
    html = '<html><head><script src="https://cdn.zid.store/js/theme.js"></script></head></html>'
    assert detect_platform_from_html(html) == "zid"


def test_detects_woocommerce_from_plugin_path():
    html = '<html><head><link href="/wp-content/plugins/woocommerce/assets/css/style.css"></head></html>'
    assert detect_platform_from_html(html) == "woocommerce"


def test_case_insensitive_matching():
    html = "<HTML><BODY>CDN.SHOPIFY.COM asset reference</BODY></HTML>"
    assert detect_platform_from_html(html) == "shopify"


def test_returns_none_for_unrecognized_platform():
    html = "<html><body><h1>Just a plain custom-built store</h1></body></html>"
    assert detect_platform_from_html(html) is None


def test_returns_none_for_empty_html():
    assert detect_platform_from_html("") is None


def test_detect_from_pages_returns_first_matching_page():
    pages = [
        "<html><body>plain homepage, no markers</body></html>",
        '<html><body><script src="https://cdn.salla.sa/js/app.js"></script></body></html>',
        "<html><body>another plain page</body></html>",
    ]
    assert detect_platform_from_pages(pages) == "salla"


def test_detect_from_pages_returns_none_when_no_page_matches():
    pages = ["<html>a</html>", "<html>b</html>"]
    assert detect_platform_from_pages(pages) is None
