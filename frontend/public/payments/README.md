# شعارات وسائل الدفع — Payment method logos

The footer's payment row loads each mark from this folder by slug. Drop
the files in with these exact names:

| File | Method |
| --- | --- |
| `stcpay.svg` | stc pay |
| `applepay.svg` | Apple Pay |
| `visa.svg` | VISA |
| `mada.svg` | mada |

A missing file degrades to the method's name as text on the same white
tile, so nothing breaks — but it costs one 404 per page load until the
asset is added.

Marks render at 20px tall inside a 40px tile, so wide wordmark artwork
works well. Use versions intended for light backgrounds; the tile is
white.
