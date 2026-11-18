import { useState, type FormEvent } from "react";
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Globe2,
  Image,
  Mic,
  Newspaper,
  Search,
  Video,
} from "lucide-react";

type WebSearchResult = {
  title: string;
  url: string;
  display_url: string;
  description: string;
};

type WebSearchResponse = {
  provider: string;
  query: string;
  page: number;
  page_size: number;
  result_count: number;
  has_more: boolean;
  results: WebSearchResult[];
};

const categories = [
  { label: "Web", icon: Globe2 },
  { label: "Images", icon: Image },
  { label: "Videos", icon: Video },
  { label: "News", icon: Newspaper },
];

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

function getDomain(value: string): string {
  try {
    return new URL(value).hostname.replace(/^www\./, "");
  } catch {
    return value;
  }
}

export default function App() {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("Web");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<WebSearchResult[]>([]);
  const [searchedQuery, setSearchedQuery] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);

  async function runSearch(nextPage = 1) {
    const term = query.trim();
    if (!term) {
      setNotice("Enter a search term to begin.");
      return;
    }
    if (category !== "Web") {
      setNotice(category + " search is planned for a later phase.");
      return;
    }

    setLoading(true);
    setNotice("");
    try {
      const params = new URLSearchParams({
        q: term,
        page: String(nextPage),
        page_size: "10",
      });
      const response = await fetch(
        API_BASE_URL + "/api/v1/web-search?" + params.toString(),
        { headers: { Accept: "application/json" } },
      );
      const payload: unknown = await response.json().catch(() => ({}));
      const data = payload as Partial<WebSearchResponse> & { detail?: string };

      if (!response.ok) {
        throw new Error(data.detail || "Search request failed.");
      }

      setResults(Array.isArray(data.results) ? data.results : []);
      setSearchedQuery(data.query || term);
      setCurrentPage(data.page || nextPage);
      setHasMore(Boolean(data.has_more));
      setHasSearched(true);
    } catch (error) {
      setResults([]);
      setHasMore(false);
      setHasSearched(false);
      setNotice(
        error instanceof Error
          ? error.message + " Check the Apokolips Search API configuration."
          : "Could not connect to the Apokolips Search API.",
      );
    } finally {
      setLoading(false);
    }
  }

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void runSearch(1);
  }

  return (
    <main className="shell">
      <header className="topbar">
        <a className="brand-small" href="/" aria-label="Apokolips Search home">
          <span className="brand-mark">A</span> APOKOLIPS
        </a>
        <span className="status"><i /> LEVEL 1 · WEB SEARCH</span>
      </header>

      <section className="hero">
        <div className="eyebrow"><span /> WEB DISCOVERY</div>
        <div className="wordmark"><span>APOKOLIPS</span><strong>SEARCH</strong></div>
        <p className="tagline">Explore. Discover. Connect.</p>
        <p className="intro">Search the web with results from a global search index.</p>

        <form className="search-form" onSubmit={submitSearch}>
          <Search size={20} aria-hidden="true" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search the web..."
            aria-label="Search the web"
            maxLength={600}
          />
          <button
            className="voice-button"
            type="button"
            aria-label="Voice search is not available yet"
            title="Voice search — coming later"
          >
            <Mic size={18} />
          </button>
          <button className="search-button" type="submit" disabled={loading}>
            {loading ? "Searching..." : "Search"} <ArrowUpRight size={16} />
          </button>
        </form>

        <nav className="categories" aria-label="Search categories">
          {categories.map(({ label, icon: Icon }) => (
            <button
              key={label}
              className={category === label ? "category active" : "category"}
              onClick={() => {
                setCategory(label);
                setResults([]);
                setHasSearched(false);
                setNotice(label === "Web" ? "" : label + " search is planned for a later phase.");
              }}
              type="button"
              disabled={label !== "Web"}
              title={label === "Web" ? "Search web pages" : label + " search — coming later"}
            >
              <Icon size={16} /> {label}
            </button>
          ))}
        </nav>

        {notice && <div className="notice" role="status">{notice}</div>}
      </section>

      {hasSearched && (
        <section className="results-section" aria-live="polite">
          <div className="results-heading">
            <div>
              <p className="results-eyebrow">WEB SEARCH RESULTS</p>
              <h1>Results for <span>“{searchedQuery}”</span></h1>
              <p className="results-count">
                {results.length.toLocaleString()} {results.length === 1 ? "result" : "results"} on this page
              </p>
            </div>
          </div>

          {results.length > 0 ? (
            <div className="results-list">
              {results.map((result) => (
                <article className="result-card" key={result.url}>
                  <div className="result-domain"><Globe2 size={13} /> {result.display_url || getDomain(result.url)}</div>
                  <h2>
                    <a href={result.url} target="_blank" rel="noopener noreferrer">
                      {result.title || result.url}
                    </a>
                  </h2>
                  <p className="result-url">{result.url}</p>
                  <p className="result-snippet">
                    {result.description || "No description is available for this page."}
                  </p>
                </article>
              ))}
            </div>
          ) : (
            <div className="empty-results">
              <Search size={23} />
              <h2>No results found</h2>
              <p>Try a different search phrase or check the spelling of your query.</p>
            </div>
          )}

          {(currentPage > 1 || hasMore) && (
            <div className="pagination">
              <button
                type="button"
                onClick={() => void runSearch(currentPage - 1)}
                disabled={loading || currentPage <= 1}
              >
                <ArrowLeft size={15} /> Previous
              </button>
              <span>Page {currentPage}</span>
              <button
                type="button"
                onClick={() => void runSearch(currentPage + 1)}
                disabled={loading || !hasMore || currentPage >= 10}
              >
                Next <ArrowRight size={15} />
              </button>
            </div>
          )}
        </section>
      )}

      <section className="principles" aria-label="Project principles">
        <article><span className="principle-number">01</span><h2>Web-wide discovery</h2><p>Explore relevant pages from a large independent web index.</p></article>
        <article><span className="principle-number">02</span><h2>Simple by design</h2><p>Clear titles, source addresses and concise descriptions.</p></article>
        <article><span className="principle-number">03</span><h2>Built in stages</h2><p>Images, video, news and Apokolips’ own index can follow in later phases.</p></article>
      </section>

      <footer>
        <span>© {new Date().getFullYear()} Apokolips Search</span>
        <span>Level 1 · Basic web search · In development</span>
      </footer>
    </main>
  );
}
