# شعارات التكاملات — Integration logos

`IntegrationsSection` in `src/app/page.tsx` loads each platform logo from
this folder by slug. Drop the files in with these exact names:

| File | Platform |
| --- | --- |
| `wordpress.svg` | WordPress |
| `shopify.svg` | Shopify |
| `framer.svg` | Framer |
| `wix.svg` | Wix |
| `notion.svg` | Notion |
| `ghost.svg` | Ghost |
| `wordpress-com.svg` | WordPress.com |
| `webhook.svg` | Webhook |

Any file that is missing degrades to a lettered tile instead of a broken
image, so the section stays presentable — but it also means a missing
file costs one 404 per page load. Add the real marks to clear those.

Square artwork works best; the section renders them at 30×30 inside a
56px tile.
