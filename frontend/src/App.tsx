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

type SearchResult = {
  id: number;
  url: string;
  canonical_url: string;
  title: string;
  description: string;
  language: string;
  snippet: string;
  relevance_score: number;
  last_crawled_at: string;
};

type SearchResponse = {
  query: string;
  total_results: number;
  page: number;
  page_size: number;
  total_pages: number;
  has_more: boolean;
  results: SearchResult[];
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
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searchedQuery, setSearchedQuery] = useState("");
  const [totalResults, setTotalResults] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [hasSearched, setHasSearched] = useState(false);

  async function runSearch(nextPage = 1) {
    const term = query.trim();
    if (!term) {
      setNotice("Enter a search term to begin.");
      return;
    }
    if (category !== "Web") {
      setNotice(category + " search is planned for a later phase. Web search uses Apokolips' local index.");
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
      const response = await fetch(API_BASE_URL + "/search?" + params.toString());
      const payload = await response.json();

      if (!response.ok) {
        const detail = typeof payload.detail === "string" ? payload.detail : "Search request failed.";
        throw new Error(detail);
      }

      const data = payload as SearchResponse;
      setResults(data.results);
      setSearchedQuery(data.query);
      setTotalResults(data.total_results);
      setCurrentPage(data.page);
      setTotalPages(data.total_pages);
      setHasSearched(true);
    } catch (error) {
      setResults([]);
      setTotalResults(0);
      setTotalPages(0);
      setHasSearched(false);
      setNotice(
        error instanceof Error
          ? error.message + " Check that the Apokolips Search API is running at " + API_BASE_URL + "."
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
        <span className="status"><i /> LOCAL INDEX SEARCH</span>
      </header>

      <section className="hero">
        <div className="eyebrow"><span /> INDEPENDENT WEB DISCOVERY</div>
        <div className="wordmark"><span>APOKOLIPS</span><strong>SEARCH</strong></div>
        <p className="tagline">Explore. Discover. Connect.</p>
        <p className="intro">A new path to the web, built on our own search technology.</p>

        <form className="search-form" onSubmit={submitSearch}>
          <Search size={20} aria-hidden="true" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search the web..."
            aria-label="Search the web"
            maxLength={200}
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
                setNotice(label === "Web" ? "" : label + " search is planned for a later phase.");
              }}
              type="button"
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
              <p className="results-eyebrow">APOKOLIPS INDEX</p>
              <h1>Results for <span>“{searchedQuery}”</span></h1>
              <p className="results-count">
                {totalResults.toLocaleString()} {totalResults === 1 ? "result" : "results"} from the local index
              </p>
            </div>
          </div>

          {results.length > 0 ? (
            <div className="results-list">
              {results.map((result) => (
                <article className="result-card" key={result.id}>
                  <div className="result-domain"><Globe2 size={13} /> {getDomain(result.canonical_url)}</div>
                  <h2>
                    <a href={result.url} target="_blank" rel="noreferrer">
                      {result.title || result.canonical_url}
                    </a>
                  </h2>
                  <p className="result-url">{result.canonical_url}</p>
                  <p className="result-snippet">{result.snippet || result.description || "No description is available for this page."}</p>
                </article>
              ))}
            </div>
          ) : (
            <div className="empty-results">
              <Search size={23} />
              <h2>No matching pages found</h2>
              <p>Try different words, or crawl a public website to add pages to the Apokolips index.</p>
            </div>
          )}

          {totalPages > 1 && (
            <div className="pagination">
              <button
                type="button"
                onClick={() => void runSearch(currentPage - 1)}
                disabled={loading || currentPage <= 1}
              >
                <ArrowLeft size={15} /> Previous
              </button>
              <span>Page {currentPage} of {totalPages}</span>
              <button
                type="button"
                onClick={() => void runSearch(currentPage + 1)}
                disabled={loading || currentPage >= totalPages}
              >
                Next <ArrowRight size={15} />
              </button>
            </div>
          )}
        </section>
      )}

      <section className="principles" aria-label="Project principles">
        <article><span className="principle-number">01</span><h2>Our own index</h2><p>Build a first-party web index with a crawler and document pipeline.</p></article>
        <article><span className="principle-number">02</span><h2>Useful by design</h2><p>Prioritise relevant, clear results and transparent ranking signals.</p></article>
        <article><span className="principle-number">03</span><h2>Respect the web</h2><p>Crawl responsibly, honour site policies and protect user privacy.</p></article>
      </section>

      <footer>
        <span>© {new Date().getFullYear()} Apokolips Search</span>
        <span>Independent search technology · In development</span>
      </footer>
    </main>
  );
}
