import csv

from iae_launch.runindex import RunIndex


def test_record_upsert_and_reload(tmp_path):
    p = tmp_path / "sub" / "process_index.csv"
    idx = RunIndex(p)
    idx.record("1_100", pid="abc", s3uri="s3://b/audit-processes/abc/", descargado=False)
    idx.record("1_100", descargado=True)
    rows = list(csv.DictReader(p.open()))
    assert rows == [{"radicado": "1_100", "pid": "abc", "descargado": "true",
                     "s3uri": "s3://b/audit-processes/abc/"}]
    again = RunIndex(p)
    again.record("2_200", pid="def")
    assert {r["radicado"] for r in csv.DictReader(p.open())} == {"1_100", "2_200"}


def test_malformed_csv_is_a_clear_error(tmp_path):
    import pytest

    from iae_launch.runindex import RunIndexError
    p = tmp_path / "i.csv"
    p.write_text("a,b\n1,2\n")
    with pytest.raises(RunIndexError, match="cabecera"):
        RunIndex(p)


def test_write_is_atomic_no_temp_left(tmp_path):
    p = tmp_path / "i.csv"
    RunIndex(p).record("1_1", pid="x")
    assert [f.name for f in tmp_path.iterdir()] == ["i.csv"]
