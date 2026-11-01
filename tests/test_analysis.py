from bot import analysis

SIGNALS = {
    "min_move_pct": 4.0,
    "z_threshold": 2.5,
    "min_move_pct_by_group": {},
    "rsi_oversold": 30,
    "near_52w_low_pct": 5.0,
    "min_drawdown_pct": 20.0,
    "max_movers": 2,
    "max_opportunities": 1,
}
MARKET = {
    "benchmark": "SPY",
    "rotation_min_gap_pct": 1.5,
    "rotation_z": 2.0,
    "sectors": [{"symbol": "SMH", "label": "Semis"}, {"symbol": "IGV", "label": "Software"}],
    "styles": [{"symbol": "IWM", "label": "Pequeñas"}],
    "rotation_pairs": [["SMH", "IGV"], ["SMH", "NOEXISTE"]],
}


def item(symbol):
    return {"symbol": symbol, "name": symbol, "group": "S&P 500", "keywords": []}


def test_required_symbols_includes_every_section():
    cfg = {"panorama": [{"symbol": "^GSPC"}], "market_analysis": MARKET}
    assert analysis.required_symbols([item("AAPL"), item("SMH")], cfg) == [
        "AAPL",
        "IGV",
        "IWM",
        "SMH",
        "SPY",
        "^GSPC",
    ]


def test_required_symbols_without_market_analysis():
    assert analysis.required_symbols([item("AAPL")], {}) == ["AAPL"]


def test_panorama_skips_missing_prices(price_frame):
    cfg = [{"symbol": "SPY", "label": "S&P"}, {"symbol": "X", "label": "Falta"}]
    panorama, last_date = analysis.build_panorama({"SPY": price_frame(0.01)}, cfg)
    assert [label for label, _ in panorama] == ["S&P"]
    assert round(panorama[0][1]) == 1
    assert last_date.strftime("%d/%m/%Y") == "30/10/2026"


def test_panorama_without_data_has_no_date():
    assert analysis.build_panorama({}, [{"symbol": "X", "label": "X"}]) == ([], None)


def test_market_analysis_is_optional():
    assert analysis.market_analysis({}, {}) == ([], [])


def test_market_analysis_names_winner_and_skips_incomplete_pairs(price_frame, caplog):
    prices = {
        "SPY": price_frame(0.0, seed=3),
        "SMH": price_frame(-0.03, seed=1),
        "IGV": price_frame(0.02, seed=2),
    }
    sectors, rotations = analysis.market_analysis(prices, MARKET)
    assert [sector["label"] for sector in sectors] == ["Software", "Semis"]
    assert rotations[0]["winner"] == "Software"
    assert rotations[0]["loser"] == "Semis"
    assert "SMH/NOEXISTE" in caplog.text


def test_market_analysis_names_first_of_the_pair_when_it_wins(price_frame):
    prices = {
        "SPY": price_frame(0.0, seed=3),
        "SMH": price_frame(0.03, seed=1),
        "IGV": price_frame(-0.02, seed=2),
    }
    _, rotations = analysis.market_analysis(prices, MARKET)
    assert rotations[0]["winner"] == "Semis"


def test_cedears_go_first_and_limits_apply(price_frame):
    prices = {
        "NOCED": price_frame(-0.30),
        "CED1": price_frame(-0.08),
        "CED2": price_frame(-0.10),
        "CALMA": price_frame(0.0),
    }
    universe = [item(s) for s in [*prices, "SINPRECIO"]]
    movers, _ = analysis.classify_assets(universe, prices, SIGNALS, {"CED1", "CED2"})
    assert [m["symbol"] for m in movers] == ["CED2", "CED1"]
    assert movers[0]["tag"] == "[CEDEAR]"


def test_opportunities_are_only_for_cedears_deepest_first(price_frame):
    # La caída del 30% y del 40% deja a los activos muy abajo de su máximo y en su mínimo
    prices = {
        "NOCED": price_frame(-0.50),
        "CED1": price_frame(-0.30),
        "CED2": price_frame(-0.40),
    }
    universe = [item(symbol) for symbol in prices]
    _, opportunities = analysis.classify_assets(universe, prices, SIGNALS, {"CED1", "CED2"})
    assert [o["symbol"] for o in opportunities] == ["CED2"]
    assert opportunities[0]["reasons"]


def test_unique_flagged_removes_repeats_and_applies_limit():
    movers = [{"symbol": "A"}, {"symbol": "B"}]
    opportunities = [{"symbol": "A", "reasons": []}, {"symbol": "C"}]
    assert [e["symbol"] for e in analysis.unique_flagged(movers, opportunities, 3)] == ["A", "B", "C"]
    assert len(analysis.unique_flagged(movers, opportunities, 1)) == 1


def test_small_sp500_companies_are_skipped_but_other_groups_stay(price_frame):
    signals_cfg = {**SIGNALS, "min_market_cap_usd_bn": 100, "max_movers": 3}
    prices = {"GRANDE": price_frame(-0.20), "CHICA": price_frame(-0.30), "YPF": price_frame(-0.10)}
    universe = [item("GRANDE"), item("CHICA"), {**item("YPF"), "group": "Argentina"}]
    caps = {"GRANDE": 300e9, "CHICA": 30e9}
    movers, _ = analysis.classify_assets(universe, prices, signals_cfg, set(), caps.get)
    assert {m["symbol"] for m in movers} == {"GRANDE", "YPF"}


def test_unknown_market_cap_stays_in_the_report(price_frame):
    signals_cfg = {**SIGNALS, "min_market_cap_usd_bn": 100}
    movers, _ = analysis.classify_assets(
        [item("X")], {"X": price_frame(-0.20)}, signals_cfg, set(), lambda symbol: None
    )
    assert [m["symbol"] for m in movers] == ["X"]


def test_market_cap_is_only_requested_until_the_limit(price_frame):
    signals_cfg = {**SIGNALS, "min_market_cap_usd_bn": 100, "max_movers": 1}
    prices = {"A": price_frame(-0.30), "B": price_frame(-0.20)}
    calls = []

    def cap(symbol):
        calls.append(symbol)
        return 300e9

    analysis.classify_assets([item("A"), item("B")], prices, signals_cfg, set(), cap)
    assert len(calls) == 1
