# Level 1 — Basic Web Search

Apokolips Search Level 1 retrieves live web results through the Brave Search API and renders them in the Apokolips Search interface.

This is a provider-powered search experience, not yet an independently operated, full-web index. The existing Apokolips Spider, SQLite FTS5 index and developer API remain in the repository as separate first-party components for later stages.

## Request flow

1. The browser sends a query to the Apokolips backend at `GET /api/v1/web-search`.
2. The backend validates the query and applies a small per-IP request limit.
3. The backend calls Brave's Web Search API using the private `BRAVE_SEARCH_API_KEY`.
4. Only the fields needed by the results page are normalized and returned.
5. Results are rendered immediately. Search responses are not stored in SQLite or cached by this application.

The Brave API key is never sent to the browser.

## Provider setup

1. Create a Brave Search API account and activate a Search plan in the Brave Search API dashboard.
2. Create an API key in the dashboard.
3. Set the key as a backend environment variable named `BRAVE_SEARCH_API_KEY`.
4. Optionally set `BRAVE_SEARCH_COUNTRY` to a two-letter country code. It defaults to `LK`.

Official resources:

- [Brave Search API dashboard](https://api-dashboard.search.brave.com/)
- [Brave Web Search API reference](https://api-dashboard.search.brave.com/api-reference/web/search/get)
- [Brave authentication guide](https://api-dashboard.search.brave.com/documentation/guides/authentication)
- [Brave Search API terms of use](https://api-dashboard.search.brave.com/documentation/resources/terms-of-service)

The Brave Search API currently requires an activated plan and payment details. The provider's dashboard shows the current plan, credits and usage; review those details before enabling a public deployment.

### Local development

Windows PowerShell:

```powershell
$env:BRAVE_SEARCH_API_KEY = "YOUR_PRIVATE_BRAVE_API_KEY"
$env:BRAVE_SEARCH_COUNTRY = "LK"
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

macOS/Linux:

```bash
export BRAVE_SEARCH_API_KEY="YOUR_PRIVATE_BRAVE_API_KEY"
export BRAVE_SEARCH_COUNTRY="LK"
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Never put the key in `frontend/.env`, a `VITE_*` variable, browser JavaScript, screenshots, GitHub issues or a committed file. Keep it in the backend host's secret manager or untracked environment.

## Endpoint

```http
GET /api/v1/web-search?q=Apokolips&page=1&page_size=10
```

Parameters:

| Parameter | Default | Limits | Purpose |
|---|---:|---:|---|
| `q` | required | 1–600 characters; at most 75 words | Search phrase |
| `page` | 1 | 1–10 | Result page |
| `page_size` | 10 | 1–20 | Results per page |

The API uses Brave's country targeting, moderate Safe Search and web-only results. The `page` parameter maps to Brave's zero-based `offset`. Pagination is driven by the provider's `more_results_available` flag; result pages may overlap, and a full result count is not provided.

Example response:

```json
{
  "provider": "Brave Search",
  "query": "Apokolips",
  "page": 1,
  "page_size": 10,
  "result_count": 1,
  "has_more": true,
  "results": [
    {
      "title": "Example result",
      "url": "https://example.com/",
      "display_url": "example.com",
      "description": "A short result description."
    }
  ]
}
```

## Limits and errors

The backend applies a default in-memory limit of 30 search requests per IP address per minute. It is intended as basic protection for a single-instance Level 1 deployment, not a distributed quota system. It resets when the process restarts. Production hosting should also configure edge/server rate limiting and provider spend alerts.

- `200` — results returned.
- `422` — invalid query or page parameters.
- `429` — this client has reached the Apokolips per-minute limit; check `Retry-After`.
- `502` — Brave could not return a valid search response.
- `503` — provider key is missing/rejected or the provider quota is temporarily unavailable.

The existing `GET /api/v1/search` endpoint remains the separate, API-key-protected search over Apokolips' own SQLite FTS5 index. It is not the provider-backed endpoint used by the Level 1 frontend.

## Provider terms and data handling

Search queries are sent to Brave to obtain results. Do not describe results as independently crawled or ranked by Apokolips. This integration does not cache search results or save them into the Apokolips index. Review Brave's current API terms and privacy requirements before public launch, including end-user restrictions and notices applicable to the application. The provider's terms prohibit retaining results beyond transient operation of the application and restrict redistribution or resale.

## Testing

Unit and API tests use a fake provider. They do not require a real Brave key and do not make billable network requests.
