from types import SimpleNamespace

from bot import universe

WIKI_HTML = """
<table>
  <tr><th>Symbol</th><th>Security</th></tr>
  <tr><td>BRK.B</td><td>Berkshire Hathaway</td></tr>
  <tr><td>AAPL</td><td>Apple Inc.</td></tr>
</table>
"""
CFG = {
    "sp500_fallback": [{"symbol": "MSFT", "name": "Microsoft"}],
    "groups": {
        "Brasil": [{"symbol": "PBR", "name": "Petrobras"}, {"symbol": "AAPL"}],
        "Materias primas": [{"symbol": "GC=F", "name": "Oro", "keywords": ["gold"]}],
    },
}


def test_fetch_sp500_converts_tickers_to_yahoo_format(monkeypatch):
    response = SimpleNamespace(text=WIKI_HTML, raise_for_status=lambda: None)
    monkeypatch.setattr(universe.requests, "get", lambda *args, **kwargs: response)
    assert universe.fetch_sp500()[0]["symbol"] == "BRK-B"


def test_build_universe_adds_groups_without_duplicates(monkeypatch):
    sp500 = [{"symbol": "AAPL", "name": "Apple", "group": "S&P 500", "keywords": []}]
    monkeypatch.setattr(universe, "fetch_sp500", lambda: sp500)
    items = universe.build_universe(CFG)
    assert [item["symbol"] for item in items] == ["AAPL", "PBR", "GC=F"]
    assert items[0]["group"] == "S&P 500"
    assert items[2]["keywords"] == ["gold"]


def test_build_universe_uses_fallback_when_wikipedia_fails(monkeypatch):
    def fail():
        raise RuntimeError("sin red")

    monkeypatch.setattr(universe, "fetch_sp500", fail)
    assert universe.build_universe(CFG)[0]["symbol"] == "MSFT"
