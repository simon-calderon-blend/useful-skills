import pytest

from iae_launch import envs, jumphost

TEST = envs.get_env("test")
CFG = TEST.bastion_instance_id


def info(*pairs):
    return {"InstanceInformationList": [{"InstanceId": i, "PingStatus": s} for i, s in pairs]}


def ec2_instance(iid, vpc, name, state="running"):
    return {"InstanceId": iid, "VpcId": vpc, "State": {"Name": state},
            "Tags": [{"Key": "Name", "Value": name}] if name else []}


def test_configured_bastion_online_wins(stubbed):
    ssm, ec2 = stubbed("ssm"), stubbed("ec2")
    ssm.ok("describe_instance_information", info((CFG, "Online")),
           Filters=[{"Key": "InstanceIds", "Values": [CFG]}])
    host = jumphost.resolve(ssm.client, ec2.client, TEST)
    assert host.instance_id == CFG and host.how == "configurado"


def test_falls_back_to_online_instance_in_api_vpc_preferring_bastion(stubbed):
    ssm, ec2 = stubbed("ssm"), stubbed("ec2")
    ssm.ok("describe_instance_information", info(), Filters=[{"Key": "InstanceIds", "Values": [CFG]}])
    ec2.ok("describe_subnets", {"Subnets": [{"SubnetId": jumphost.SUBNETS["test"], "VpcId": "vpc-api"}]},
           SubnetIds=[jumphost.SUBNETS["test"]])
    ssm.ok("describe_instance_information", info(("i-aaa", "Online"), ("i-bbb", "Online"),
                                                  ("i-ccc", "Online"), ("i-ddd", "ConnectionLost")))
    ec2.ok("describe_instances", {"Reservations": [{"Instances": [
        ec2_instance("i-aaa", "vpc-other", "adr-test-bastion-x"),
        ec2_instance("i-bbb", "vpc-api", "worker"),
        ec2_instance("i-ccc", "vpc-api", "adr-test-bastion-connect-azure")]}]},
        InstanceIds=["i-aaa", "i-bbb", "i-ccc"])
    host = jumphost.resolve(ssm.client, ec2.client, TEST)
    assert host.instance_id == "i-ccc" and host.name == "adr-test-bastion-connect-azure"
    assert "VPC" in host.how


def test_any_online_in_vpc_when_no_bastion_name(stubbed):
    ssm, ec2 = stubbed("ssm"), stubbed("ec2")
    ssm.ok("describe_instance_information", info(), Filters=[{"Key": "InstanceIds", "Values": [CFG]}])
    ec2.ok("describe_subnets", {"Subnets": [{"SubnetId": jumphost.SUBNETS["test"], "VpcId": "vpc-api"}]},
           SubnetIds=[jumphost.SUBNETS["test"]])
    ssm.ok("describe_instance_information", info(("i-bbb", "Online")))
    ec2.ok("describe_instances", {"Reservations": [{"Instances": [ec2_instance("i-bbb", "vpc-api", None)]}]},
           InstanceIds=["i-bbb"])
    assert jumphost.resolve(ssm.client, ec2.client, TEST).instance_id == "i-bbb"


def test_none_available_raises(stubbed):
    ssm, ec2 = stubbed("ssm"), stubbed("ec2")
    ssm.ok("describe_instance_information", info(), Filters=[{"Key": "InstanceIds", "Values": [CFG]}])
    ec2.ok("describe_subnets", {"Subnets": [{"SubnetId": jumphost.SUBNETS["test"], "VpcId": "vpc-api"}]},
           SubnetIds=[jumphost.SUBNETS["test"]])
    ssm.ok("describe_instance_information", info())
    with pytest.raises(jumphost.JumpHostError, match="vpc-api"):
        jumphost.resolve(ssm.client, ec2.client, TEST)
