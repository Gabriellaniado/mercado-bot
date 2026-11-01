from types import SimpleNamespace

from bot import news

TRUSTED = ["reuters", "cnbc", "ámbito"]


def test_trusted_by_source_or_url():
    assert news.is_trusted("Reuters", "", TRUSTED)
    assert news.is_trusted("", "https://www.cnbc.com/x", TRUSTED)
    assert not news.is_trusted("Blog random", "https://spam.example/x", TRUSTED)


def test_yahoo_new_and_old_formats():
    new = {
        "content": {
            "title": "A",
            "provider": {"displayName": "Reuters"},
            "canonicalUrl": {"url": "https://r.com/a"},
        }
    }
    old = {"title": "B", "publisher": "CNBC", "link": "https://cnbc.com/b"}
    assert news.normalize_yahoo_item(new) == {"title": "A", "source": "Reuters", "url": "https://r.com/a"}
    assert news.normalize_yahoo_item(old)["source"] == "CNBC"
    assert news.normalize_yahoo_item({}) is None


def test_headline_matching():
    assert news.headline_matches("Apple shares jump after earnings", "AAPL", "Apple Inc.")
    assert news.headline_matches("Gold hits record high", "GC=F", "Oro", ["gold"])
    assert news.headline_matches("Why AAPL moved", "AAPL", "x")
    assert news.headline_matches("$V is up", "V", "x")
    assert not news.headline_matches("Appleton opens new plant", "AAPL", "Apple Inc.")
    # Un ticker corto no debe generar falsos positivos
    assert not news.headline_matches("Why the V-shaped recovery failed", "V", "Visa Inc.")


def test_collect_news_filters_untrusted_and_dedupes():
    flagged = [{"symbol": "AAPL", "name": "Apple Inc.", "keywords": []}]
    feed_items = [
        {"title": "Apple raises guidance", "source": "CNBC", "url": ""},
        {"title": "Apple raises guidance", "source": "CNBC", "url": ""},
        {"title": "Apple secret rumor!!!", "source": "Blog random", "url": "https://spam.example"},
    ]
    result = news.collect_news(flagged, feed_items, TRUSTED, fetch_yahoo=lambda s: [])
    assert [n["title"] for n in result["AAPL"]] == ["Apple raises guidance"]


def test_collect_news_respects_limit_per_symbol():
    flagged = [{"symbol": "AAPL", "name": "Apple", "keywords": []}]
    items = [{"title": f"Apple news {i}", "source": "CNBC", "url": ""} for i in range(5)]
    result = news.collect_news(flagged, items, TRUSTED, per_symbol=2, fetch_yahoo=lambda s: [])
    assert len(result["AAPL"]) == 2


def test_yahoo_news_normalizes_and_drops_empty(monkeypatch):
    ticker = SimpleNamespace(news=[{"title": " A ", "publisher": "CNBC", "link": "u"}, {}])
    monkeypatch.setattr(news.yf, "Ticker", lambda symbol: ticker)
    assert news.yahoo_news("AAPL") == [{"title": "A", "source": "CNBC", "url": "u"}]


def test_yahoo_news_survives_errors(monkeypatch):
    def fail(symbol):
        raise RuntimeError("sin red")

    monkeypatch.setattr(news.yf, "Ticker", fail)
    assert news.yahoo_news("AAPL") == []


def test_fetch_feed_items_skips_empty_feed_and_warns(monkeypatch, caplog):
    entry = SimpleNamespace(title=" Titular ", link="https://x")
    results = {"bueno": [entry, SimpleNamespace(title=" ", link="")], "vacio": []}
    monkeypatch.setattr(news.feedparser, "parse", lambda url, agent: SimpleNamespace(entries=results[url]))
    items = news.fetch_feed_items([{"name": "A", "url": "bueno"}, {"name": "B", "url": "vacio"}])
    assert items == [{"title": "Titular", "source": "A", "url": "https://x"}]
    assert "Feed sin noticias, lo salto: B" in caplog.text
