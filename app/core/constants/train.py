from enum import Enum

class TrainType(str, Enum):
    RAJDHANI       = "rajdhani"
    SHATABDI       = "shatabdi"
    JAN_SHATABDI   = "jan_shatabdi"
    DURONTO        = "duronto"
    GARIB_RATH     = "garib_rath"
    SUPERFAST      = "superfast"
    EXPRESS        = "express"
    PASSENGER      = "passenger"
    SUBURBAN       = "suburban"
    DEMU           = "demu"
    SPECIAL        = "special"
    HERITAGE       = "heritage"
    UNKNOWN        = "unknown"