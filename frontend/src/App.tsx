import { useState } from "react";
import { ArrowUpRight, Globe2, Image, Mic, Newspaper, Search, Video } from "lucide-react";

const categories = [
  { label: "Web", icon: Globe2 },
  { label: "Images", icon: Image },
  { label: "Videos", icon: Video },
  { label: "News", icon: Newspaper },
];

export default function App() {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("Web");
  const [notice, setNotice] = useState("");

  function submitSearch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!query.trim()) return;
    setNotice("The independent search index is not connected yet. Search API and crawler integration are planned for the next phases.");
  }

  return (
    <main className="shell">
      <header className="topbar">
        <a className="brand-small" href="/" aria-label="Apokolips Search home"><span className="brand-mark">A</span> APOKOLIPS</a>
        <span className="status"><i /> FOUNDATION PREVIEW</span>
      </header>
      <section className="hero">
        <div className="eyebrow"><span /> INDEPENDENT WEB DISCOVERY</div>
        <div className="wordmark"><span>APOKOLIPS</span><strong>SEARCH</strong></div>
        <p className="tagline">Explore. Discover. Connect.</p>
        <p className="intro">A new path to the web, built on our own search technology.</p>
        <form className="search-form" onSubmit={submitSearch}>
          <Search size={20} aria-hidden="true" />
          <input value={query} onChange={(event) => { setQuery(event.target.value); setNotice(""); }} placeholder="Search the web..." aria-label="Search the web" />
          <button className="voice-button" type="button" aria-label="Voice search is not available yet" title="Voice search — coming later"><Mic size={18} /></button>
          <button className="search-button" type="submit">Search <ArrowUpRight size={16} /></button>
        </form>
        <nav className="categories" aria-label="Search categories">
          {categories.map(({ label, icon: Icon }) => (
            <button key={label} className={category === label ? "category active" : "category"} onClick={() => { setCategory(label); setNotice(label === "Web" ? "" : label + " search is planned for a later phase."); }} type="button">
              <Icon size={16} /> {label}
            </button>
          ))}
        </nav>
        {notice && <div className="notice" role="status">{notice}</div>}
      </section>
      <section className="principles" aria-label="Project principles">
        <article><span className="principle-number">01</span><h2>Our own index</h2><p>Build a first-party web index with a crawler and document pipeline.</p></article>
        <article><span className="principle-number">02</span><h2>Useful by design</h2><p>Prioritise relevant, clear results and transparent ranking signals.</p></article>
        <article><span className="principle-number">03</span><h2>Respect the web</h2><p>Crawl responsibly, honour site policies and protect user privacy.</p></article>
      </section>
      <footer><span>© {new Date().getFullYear()} Apokolips Search</span><span>Independent search technology · In development</span></footer>
    </main>
  );
}