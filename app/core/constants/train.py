from enum import Enum


class TrainType(str, Enum):
    RAJDHANI = "rajdhani"
    SHATABDI = "shatabdi"
    JAN_SHATABDI = "jan_shatabdi"
    DURONTO = "duronto"
    GARIB_RATH = "garib_rath"
    SUPERFAST = "superfast"
    EXPRESS = "express"
    PASSENGER = "passenger"
    SUBURBAN = "suburban"
    DEMU = "demu"
    SPECIAL = "special"
    HERITAGE = "heritage"
    UNKNOWN = "unknown"


class TrainClass(str, Enum):
    SLEEPER = "SL"
    AC_3_TIER = "3A"
    AC_2_TIER = "2A"
    AC_1_TIER = "1A"
    AC_CHAIR = "CC"
    SECOND_SITTING = "2S"
    FIRST_CLASS = "FC"
    AC_3_ECONOMY = "3E"
