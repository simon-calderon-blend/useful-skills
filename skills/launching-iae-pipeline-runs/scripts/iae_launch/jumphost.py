"""Resolución en vivo del jump host para el túnel SSM.

Los bastiones estáticos de envs.py pueden estar detenidos (test: sin volumen raíz;
dev: stopped). Se usa el configurado si está Online en SSM; si no, cualquier
instancia SSM-Online en la VPC del API (derivada de la subred conocida del ambiente,
sin hardcodear la VPC), prefiriendo nombres con "bastion". Siempre se valida después
con el sondeo GET /proceso/<uuid4> == 404.
"""

from __future__ import annotations

from dataclasses import dataclass

from .envs import EnvSpec

# Subredes del ambiente (de ahí se deriva la VPC del API).
SUBNETS = {"test": "subnet-0caad665bbd789115", "dev": "subnet-038ad5c2f9a8c0994"}


class JumpHostError(RuntimeError):
    pass


@dataclass(frozen=True)
class JumpHost:
    instance_id: str
    name: str
    how: str


def _online(ssm, ids: list[str] | None = None) -> list[str]:
    kwargs = {"Filters": [{"Key": "InstanceIds", "Values": ids}]} if ids else {}
    out: list[str] = []
    for page in ssm.get_paginator("describe_instance_information").paginate(**kwargs):
        out += [i["InstanceId"] for i in page["InstanceInformationList"] if i.get("PingStatus") == "Online"]
    return out


def _name(instance: dict) -> str:
    return next((t["Value"] for t in instance.get("Tags", []) if t["Key"] == "Name"), "")


def resolve(ssm, ec2, spec: EnvSpec) -> JumpHost:
    if spec.bastion_instance_id in _online(ssm, [spec.bastion_instance_id]):
        return JumpHost(spec.bastion_instance_id, "", "configurado")
    subnet = SUBNETS[spec.name]
    vpc = ec2.describe_subnets(SubnetIds=[subnet])["Subnets"][0]["VpcId"]
    candidates = _online(ssm)
    instances: list[dict] = []
    if candidates:
        for page in ec2.get_paginator("describe_instances").paginate(InstanceIds=candidates):
            for res in page["Reservations"]:
                instances += res["Instances"]
    in_vpc = sorted((i for i in instances if i.get("VpcId") == vpc
                     and i.get("State", {}).get("Name") == "running"),
                    key=lambda i: ("bastion" not in _name(i).lower(), _name(i), i["InstanceId"]))
    if not in_vpc:
        raise JumpHostError(f"ninguna instancia SSM-Online en la VPC {vpc} del API de {spec.name} "
                            f"(el bastión configurado {spec.bastion_instance_id} no está Online)")
    pick = in_vpc[0]
    return JumpHost(pick["InstanceId"], _name(pick), f"instancia SSM-Online en la VPC {vpc}")
