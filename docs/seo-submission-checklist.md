# Search engine submission checklist

One-time manual setup after the SEO-baseline code change deploys. Steps
in order. Take note of verification tokens; if Cloudflare changes
ownership, you'll need to re-verify.

## Google Search Console

1. Open https://search.google.com/search-console
2. "Add property" → "Domain" → enter `hotmap.cam`
3. Google shows a TXT record to add. Open Cloudflare dashboard → hotmap.cam
   → DNS → Records → Add record. Type=TXT, Name=`@`, Content=the value
   Google gave you. TTL=Auto.
4. Wait 1-2 minutes, click "Verify" in GSC. Should succeed.
5. In GSC sidebar: Sitemaps → enter `sitemap.xml` → Submit.
6. Check back in 24-48 hours: Coverage report should show URLs starting
   to be indexed. Index → Pages.

## Bing Webmaster Tools

1. Open https://www.bing.com/webmasters
2. Sign in (Microsoft account).
3. "Add a site" → enter `https://hotmap.cam/`
4. Choose "Import from Google Search Console" if available — Bing accepts
   the GSC verification automatically. Otherwise add the TXT record Bing
   provides via the same CF DNS flow as step 3 above.
5. Sitemaps → enter `https://hotmap.cam/sitemap.xml` → Submit.

## Yandex Webmaster

**Skipped.** We don't target RF traffic, and registering with Yandex
ties the domain to a Russian agency's records. See the legal-risks
discussion notes for rationale.

## Verification

After 48 hours, sanity check that indexing is happening:

```bash
# Should return some results (or "no results yet" while indexing is in progress)
curl -s "https://www.google.com/search?q=site:hotmap.cam" | grep -c "hotmap.cam"
curl -s "https://www.bing.com/search?q=site:hotmap.cam" | grep -c "hotmap.cam"
```

If 0 results after a week, check GSC Coverage report for errors —
canonical mismatches and noindex tags are the usual suspects.

## Re-submission triggers

Re-submit the sitemap (in GSC + Bing) whenever:
- URL structure changes (new page types like categories, countries)
- Many pages added or removed in one day (>20% of total URLs)
- Site moves to a new domain

For daily snapshot updates (which only change `<lastmod>` in existing
URLs), no re-submission needed. Google re-crawls based on `changefreq`.
