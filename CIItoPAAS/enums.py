from enum import Enum


class AccountRole(Enum):

    BENCHMARKING_ASSOCIATE = "BENCHMARKING_ASSOCIATE"
    CII_STAFF = "CII_STAFF"
    LAB_MANAGER = "LAB_MANAGER"

    @classmethod
    def choices(cls):
        return tuple((i.name, i.value) for i in cls)


class MembershipLevel(Enum):
    TRIAL = "TRIAL"
    STANDARD = "STANDARD"
    PREMIUM = "PREMIUM"
    INACTIVE = "INACTIVE"

    @classmethod
    def choices(cls):
        return tuple((i.name, i.value) for i in cls)


