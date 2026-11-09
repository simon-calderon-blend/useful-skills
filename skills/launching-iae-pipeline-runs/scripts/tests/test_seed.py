from botocore.stub import ANY

from iae_launch import seed
from iae_launch.seed import SeedItem


def test_content_type():
    assert seed.content_type_for("a.pdf") == "application/pdf"
    assert seed.content_type_for("a.json") == "application/json"
    assert seed.content_type_for("a.zzzzz") == "application/octet-stream"


def test_seed_put_and_copy(stubbed, tmp_path):
    f = tmp_path / "x.pdf"
    f.write_bytes(b"pdf")
    s3 = stubbed("s3")
    s3.ok("put_object", {}, Bucket="b", Key="audit-processes/pid/raw/x.pdf", Body=ANY,
          ContentType="application/pdf")
    s3.ok("copy_object", {}, Bucket="b", Key="audit-processes/pid/art/F.json",
          CopySource={"Bucket": "src", "Key": "k/F.json"}, ContentType="application/json",
          MetadataDirective="REPLACE")
    keys = seed.seed_items(s3.client, "b", "audit-processes", "pid", [
        SeedItem("put", str(f), "raw/x.pdf", "application/pdf"),
        SeedItem("copy", "s3://src/k/F.json", "art/F.json", "application/json")])
    assert keys == ["audit-processes/pid/raw/x.pdf", "audit-processes/pid/art/F.json"]


def test_hidden_items_skipped(stubbed, tmp_path):
    s3 = stubbed("s3")
    assert seed.seed_items(s3.client, "b", "p", "pid", [
        SeedItem("put", str(tmp_path / ".DS_Store"), "raw/.DS_Store", "x")]) == []


def test_parse_s3_uri():
    assert seed.parse_s3_uri("s3://b/a/b.json") == ("b", "a/b.json")


def test_copy_without_content_type_preserves_metadata(stubbed):
    s3 = stubbed("s3")
    s3.ok("copy_object", {}, Bucket="b", Key="audit-processes/pid/raw/x.pdf",
          CopySource={"Bucket": "src", "Key": "old/x.pdf"}, MetadataDirective="COPY")
    seed.seed_items(s3.client, "b", "audit-processes", "pid",
                    [SeedItem("copy", "s3://src/old/x.pdf", "raw/x.pdf", "")])


def test_copy_over_5gb_rejected():
    import pytest
    with pytest.raises(ValueError, match="5 GB"):
        seed.check_copy_size("raw/big.pdf", 6 * 1024 ** 3)
