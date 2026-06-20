from enum import Enum


class TrainType(str, Enum):
    RAJDHANI = "RAJDHANI"
    SHATABDI = "SHATABDI"
    JAN_SHATABDI = "JAN_SHATABDI"
    DURONTO = "DURONTO"
    GARIB_RATH = "GARIB_RATH"
    SUPERFAST = "SUPERFAST"
    EXPRESS = "EXPRESS"
    PASSENGER = "PASSENGER"
    SUBURBAN = "SUBURBAN"
    DEMU = "DEMU"
    SPECIAL = "SPECIAL"
    HERITAGE = "HERITAGE"
    UNKNOWN = "UNKNOWN"


class TrainClass(str, Enum):
    SLEEPER = "SL"
    AC_3_TIER = "3A"
    AC_2_TIER = "2A"
    AC_1_TIER = "1A"
    AC_CHAIR = "CC"
    SECOND_SITTING = "2S"
    FIRST_CLASS = "FC"
    AC_3_ECONOMY = "3E"


class Quota(str, Enum):
    GENERAL = "GN"
    TATKAL = "TQ"
    PREMIUM_TATKAL = "PT"
    LADIES = "LD"
    LOWER_BERTH = "LB"
    HANDICAPPED = "HP"
    DEFENCE = "DF"
    SENIOR_CITIZEN = "SS"
    FOREIGN_TOURIST = "FT"


class BerthType(str, Enum):
    LOWER = "LB"
    MIDDLE = "MB"
    UPPER = "UB"
    SIDE_LOWER = "SL"
    SIDE_UPPER = "SU"
    SEAT = "SEAT"  # CC / 2S coaches
    NP = "NP"
