"""Tests for named scan templates (~/.config/finresearch/scans.toml layer)."""

import pytest

try:
    import tomllib
except ImportError:  # py3.10: stdlib tomllib is 3.11+
    import tomli as tomllib

from finresearch import market_scan as ms


@pytest.fixture
def cfg_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("FINRESEARCH_CONFIG_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def defaults(monkeypatch):
    monkeypatch.setattr(ms, "SCAN_DEFAULTS", {
        "region": "us", "sector": None, "industry": None,
        "sort": "mktcap", "limit": 20, "ascending": False,
        "shortfloat_min": None, "dtc_min": None, "price": None,
    })


class _A:
    def __init__(self, **kw):
        self.region, self.sector, self.industry = "us", None, None
        self.sort, self.limit, self.ascending = "mktcap", 20, False
        self.shortfloat_min = self.dtc_min = self.price = None
        self.name = self.desc = None
        self.__dict__.update(kw)


class TestValidate:
    def test_unknown_key_raises_with_path(self, cfg_dir):
        with pytest.raises(ValueError, match="unknown key 'foo'"):
            ms.validate_template("t1", {"foo": 1})

    def test_range_must_be_pair(self, cfg_dir):
        with pytest.raises(ValueError, match="must be"):
            ms.validate_template("t1", {"price": [5, 100, 200]})

    def test_valid_keys_pass(self, cfg_dir, defaults):
        tpl = {"price": [2.0, 50.0], "shortfloat-min": 15.0, "region": "us",
               "sort": "shortfloat", "limit": 25, "ascending": True}
        assert ms.validate_template("t1", tpl) == tpl
        assert ms.validate_template("t2", {"description": "x"}) == {"description": "x"}


class TestApply:
    def test_template_wins_over_defaults(self, defaults):
        args = _A()
        ms.apply_template(args, {"shortfloat-min": 15, "sort": "shortfloat"})
        assert args.shortfloat_min == 15 and args.sort == "shortfloat"

    def test_cli_set_value_beats_template(self, defaults):
        args = _A(limit=5, shortfloat_min=30)
        ms.apply_template(args, {"shortfloat-min": 15, "limit": 77, "dtc-min": 4})
        assert args.limit == 5 and args.shortfloat_min == 30
        assert args.dtc_min == 4  # CLI-untouched field still applied


class TestSaveLoadRoundTrip:
    def test_new_template_written_and_parses(self, cfg_dir, defaults):
        p = ms.save_scan("myscan", _A(price=[5.0, 100.0], desc="my value scan",
                                      shortfloat_min=5))
        assert p.exists()
        data = tomllib.load(open(p, "rb"))
        assert data["myscan"]["price"] == [5.0, 100.0]
        assert data["myscan"]["shortfloat-min"] == 5.0
        assert data["myscan"]["description"] == "my value scan"
        # noisy defaults are never persisted
        assert "region" not in data["myscan"] and "limit" not in data["myscan"]

    def test_replace_carries_description(self, cfg_dir, defaults):
        ms.save_scan("s2", _A(shortfloat_min=15, desc="watch this"))
        ms.save_scan("s2", _A(shortfloat_min=20))  # no --desc: must carry
        data = ms.load_scans()
        assert data["s2"]["description"] == "watch this"
        assert data["s2"]["shortfloat-min"] == 20.0

    def test_replace_updates_desc_when_given(self, cfg_dir, defaults):
        ms.save_scan("s3", _A(shortfloat_min=15, desc="old"))
        ms.save_scan("s3", _A(shortfloat_min=20, desc="new"))
        assert ms.load_scans()["s3"]["description"] == "new"

    def test_other_templates_survive_replace(self, cfg_dir, defaults):
        ms.save_scan("a", _A(shortfloat_min=10))
        ms.save_scan("b", _A(dtc_min=3))
        ms.save_scan("a", _A(shortfloat_min=12))
        scans = ms.load_scans()
        assert scans["a"]["shortfloat-min"] == 12.0
        assert scans["b"]["dtc-min"] == 3.0

    def test_load_missing_file_empty(self, cfg_dir):
        assert ms.load_scans() == {}

    def test_corrupt_file_warns_not_crashes(self, cfg_dir):
        (cfg_dir / "scans.toml").write_text("[not [valid tomo")
        assert ms.load_scans() == {}


class TestOneOffQuery:
    def test_flags_without_name_count_as_a_query(self, defaults):
        assert not ms.has_query(_A())
        assert ms.has_query(_A(price=[5.0, 100.0]))
        assert ms.has_query(_A(region="jp"))
