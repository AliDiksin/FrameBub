"""Street Fighter 6 character and input alias maps for parsers and quiz."""

from copy import deepcopy
from .sf6_aliases_core import CHARACTER_INPUT_ALIASES as _CORE_CHARACTER_INPUT_ALIASES
from .sf6_aliases_specials import CHARACTER_INPUT_ALIASES as _SPECIAL_CHARACTER_INPUT_ALIASES
from .sf6_aliases_roster import CHARACTER_INPUT_ALIASES as _ROSTER_CHARACTER_INPUT_ALIASES

_CHARACTER_INPUT_ALIAS_SHARDS = (
    _CORE_CHARACTER_INPUT_ALIASES,
    _SPECIAL_CHARACTER_INPUT_ALIASES,
    _ROSTER_CHARACTER_INPUT_ALIASES,
)

CHARACTER_ALIASES = {
    "kim": "kimberly",
    "gief": "zangief",
    "sim": "dhalsim",
    "aksel": "alex",
    "chun": "chun-li",
    "dj": "dee jay",
    "deejay": "dee jay",
    "honda": "e.honda",
    "bison": "m.bison",
    "m bison": "m.bison",
    "dictator": "m.bison",
    "viper": "c.viper",
    "c viper": "c.viper",
    "cviper": "c.viper",
    "bosch": "luke",
    "aki": "a.k.i",
    "a.k.i": "a.k.i",
    "a.k.i.": "a.k.i",
}

INPUT_ALIASES = {
        # DP/SRK
        "dp": "623",
        "srk": "623",
        "shoryu": "623",
        "shoryuken": "623",
        "hadoken": "fireball",
        "hadouken": "fireball",
        "denjin fireball": "denjin hadoken",
        "ex denjin fireball": "od denjin hadoken",
        "od denjin fireball": "od denjin hadoken",
        "ex denjin hadoken": "od denjin hadoken",
        # Global Super Art level aliases
        "sa1": "super art level 1",
        "sa2": "super art level 2",
        "sa3": "super art level 3",
        "level 1": "super art level 1",
        "level 2": "super art level 2",
        "level 3": "super art level 3",
        "lvl1": "super art level 1",
        "lvl2": "super art level 2",
        "lvl3": "super art level 3",
        "lv1": "super art level 1",
        "lv2": "super art level 2",
        "lv3": "super art level 3",
        "ca": "critical art",
        "critical": "critical art",
        "critical art": "critical art",
        "raging demon": "shun goku satsu",
        "sway": "juggling sway",
        "juggling sway": "juggling sway",
        "jus cool": "jus cool",
        "juscool": "jus cool",
        # Zangief SPD
        "360": "screw piledriver",
        "spd": "screw piledriver",
        "360p": "screw piledriver",
        "360+lp": "lp screw piledriver",
        "360+mp": "mp screw piledriver",
        "360+hp": "hp screw piledriver",
        "360+pp": "od screw piledriver",
        "360lp": "lp screw piledriver",
        "360mp": "mp screw piledriver",
        "360hp": "hp screw piledriver",
        "360pp": "od screw piledriver",
        "l spd": "lp screw piledriver",
        "m spd": "mp screw piledriver",
        "h spd": "hp screw piledriver",
        "od spd": "od screw piledriver",
        "ex spd": "od screw piledriver",
        "lspd": "lp screw piledriver",
        "mspd": "mp screw piledriver",
        "hspd": "hp screw piledriver",
        "light spd": "lp screw piledriver",
        "medium spd": "mp screw piledriver",
        "heavy spd": "hp screw piledriver",
        # Chun-Li Serenity Stream
        "stance": "serenity stream",
        "ss": "serenity stream",
        "stance lp": "orchid palm",
        "stance mp": "snake strike",
        "stance hp": "lotus fist",
        "stance lk": "forward strike",
        "stance mk": "senpu kick",
        "stance hk": "tenku kick",
        "stance light punch": "orchid palm",
        "stance medium punch": "snake strike",
        "stance heavy punch": "lotus fist",
        "stance light kick": "forward strike",
        "stance medium kick": "senpu kick",
        "stance heavy kick": "tenku kick",
        "ss lp": "orchid palm",
        "ss mp": "snake strike",
        "ss hp": "lotus fist",
        "ss lk": "forward strike",
        "ss mk": "senpu kick",
        "ss hk": "tenku kick",
        "ss light punch": "orchid palm",
        "ss medium punch": "snake strike",
        "ss heavy punch": "lotus fist",
        "ss light kick": "forward strike",
        "ss medium kick": "senpu kick",
        "ss heavy kick": "tenku kick",
        # Lily Mexican Typhoon
        "typhoon": "mexican typhoon",
        "mexican typhoon": "mexican typhoon",
        "l typhoon": "lp mexican typhoon",
        "m typhoon": "mp mexican typhoon",
        "h typhoon": "hp mexican typhoon",
        "od typhoon": "od mexican typhoon",
        "ex typhoon": "od mexican typhoon",
        "light typhoon": "lp mexican typhoon",
        "medium typhoon": "mp mexican typhoon",
        "heavy typhoon": "hp mexican typhoon",
    }

CHARACTER_INPUT_ALIASES = {}
for _alias_shard in _CHARACTER_INPUT_ALIAS_SHARDS:
    CHARACTER_INPUT_ALIASES.update(_alias_shard)

COMMAND_JUMP_NORMAL_ALIASES = {
        "a.k.i": {
            "j2hp": "gong fu",
            "j.2hp": "gong fu",
            "jump 2hp": "gong fu",
            "anal sodomy": "gong fu",
            "get out of jail free card": "gong fu",
        },
        "akuma": {
            "j2mk": "tenmaku blade kick",
            "j.2mk": "tenmaku blade kick",
            "jump 2mk": "tenmaku blade kick",
        },
        "chun-li": {
            "j2mk": "yoso kick",
            "j.2mk": "yoso kick",
            "jump 2mk": "yoso kick",
        },
        "dee jay": {
            "j2lk": "knee shot",
            "j.2lk": "knee shot",
            "jump 2lk": "knee shot",
        },
        "dhalsim": {
            "j2lp": "yoga mummy",
            "j.2lp": "yoga mummy",
            "jump 2lp": "yoga mummy",
            "j2k": "lk drill kick",
            "j.2k": "lk drill kick",
            "jump 2k": "lk drill kick",
            "j2lk": "lk drill kick",
            "j2mk": "mk drill kick",
            "j2hk": "hk drill kick",
        },
        "alex": {
            "j2hp": "flying cross chop",
            "j.2hp": "flying cross chop",
            "jump 2hp": "flying cross chop",
            "stance": "prowler stance",
            "stance jab": "palm jab",
            "stance lp": "palm jab",
            "stance shoulder": "shoulder launcher",
            "stance mp": "shoulder launcher",
            "stance lariat": "heavy lariat",
            "stance hp": "heavy lariat",
            "stance hop": "tactical hop",
            "stance lk": "tactical hop",
            "stance stomp": "air stampede",
            "stance mk": "air stampede",
            "stance hk": "sweep combination 1",
            "stance hk hk": "sweep combination 2",
            "stance throw": "hyper takedown",
            "stance lplk": "hyper takedown",
            "stance 5lplk": "hyper takedown",
            "stance command grab": "dangerous armbar",
            "stance 2lplk": "dangerous armbar",
            "stance 6p": "slashing elbow",
            "2pp 6p": "slashing elbow",
            "stance 6": "low rush",
            "2pp 6": "low rush",
            "stance 4": "low retreat",
            "2pp 4": "low retreat",
            "2pp lp": "palm jab",
            "2pp 5lp": "palm jab",
            "2pp mp": "shoulder launcher",
            "2pp 5mp": "shoulder launcher",
            "2pp hp": "heavy lariat",
            "2pp 5hp": "heavy lariat",
            "2pp lk": "tactical hop",
            "2pp 5lk": "tactical hop",
            "2pp mk": "air stampede",
            "2pp 5mk": "air stampede",
            "2pp hk": "sweep combination 1",
            "2pp 5hk": "sweep combination 1",
            "2pp hk hk": "sweep combination 2",
            "2pp 5hk 5hk": "sweep combination 2",
            "2pp lplk": "hyper takedown",
            "2pp 5lplk": "hyper takedown",
            "2pp 2lplk": "dangerous armbar",
            "hold hp": "stand hp (hold)",
            "held hp": "stand hp (hold)",
            "charged hp": "stand hp (hold)",
            "hold hk": "stand hk (hold)",
            "held hk": "stand hk (hold)",
            "charged hk": "stand hk (hold)",
        },
        "e.honda": {
            "j2mk": "flying sumo press",
            "j.2mk": "flying sumo press",
            "jump 2mk": "flying sumo press",
        },
        "lily": {
            "j2hp": "great spin",
            "j.2hp": "great spin",
            "jump 2hp": "great spin",
        },
        "rashid": {
            "j2hp": "blitz strike",
            "j.2hp": "blitz strike",
            "jump 2hp": "blitz strike",
        },
        "zangief": {
            "j2hp": "flying body press",
            "j.2hp": "flying body press",
            "jump 2hp": "flying body press",
        },
        "kimberly": {
            "j2mp": "elbow drop",
            "j.2mp": "elbow drop",
            "jump 2mp": "elbow drop",
            "j2mp elbow": "elbow drop",
            "j2mp(elbow)": "elbow drop",
        },
    }

for alias_char, alias_map in COMMAND_JUMP_NORMAL_ALIASES.items():
    CHARACTER_INPUT_ALIASES.setdefault(alias_char, {}).update(alias_map)

DP_PREFIX_EXCEPTIONS = {
        "marisa": ["phalanx"],
        "ken": ["dragonlash"],
        "viper": ["seismo"],
        "c.viper": ["seismo"],
    }


# SF6 {Character}Stats sheet query aliases (FAT ODS). Notation tokens use word boundaries
# via contains_token_sequence() in sf6_character_stats.match_stat_keys_in_text().
SF6_STAT_NOTATION_ALIASES = {
    "66": ("fDash", "fDashDist"),
    "44": ("bDash", "bDashDist"),
    "8": ("nJump",),
    "7": ("bJump", "bJumpDist"),
    "9": ("fJump", "fJumpDist"),
}

SF6_STAT_TOKEN_SEQUENCE_ALIASES = (
    (("6", "6"), ("fDash", "fDashDist")),
    (("4", "4"), ("bDash", "bDashDist")),
)

SF6_STAT_PHRASE_ALIASES = (
    (("health", "hp", "life bar", "life"), ("health",)),
    (("best reversal", "reversal", "reversals", "defensive reversal"), ("bestReversal",)),
    (
        ("forward dash", "f dash", "fdash", "front dash", "forward 66", "f66"),
        ("fDash", "fDashDist"),
    ),
    (
        ("back dash", "b dash", "bdash", "backwards dash", "backward dash", "back 44", "b44"),
        ("bDash", "bDashDist"),
    ),
    (("dash speed", "dash frame", "dash frames", "dashes", "dash"), ("fDash", "bDash", "fDashDist", "bDashDist")),
    (("neutral jump", "n jump", "normal jump", "8 jump"), ("nJump",)),
    (("forward jump", "f jump", "9 jump"), ("fJump", "fJumpDist")),
    (("back jump", "b jump", "7 jump"), ("bJump", "bJumpDist")),
    (("jump distance", "jump dist", "jump distances"), ("fJumpDist", "bJumpDist", "nJump", "fJump", "bJump")),
    (("jump", "jumps"), ("nJump", "fJump", "bJump")),
    (("forward walk", "f walk", "walk forward"), ("fWalk",)),
    (("back walk", "b walk", "walk back", "backward walk"), ("bWalk",)),
    (("walk speed", "walk speeds", "walk"), ("fWalk", "bWalk")),
    (
        ("drive rush", "drive rush distance", "dr distance", "dr dist", "drive rush dist", "dr"),
        ("dRushDist", "dRushDistMin", "dRushDistBlock", "dRushDistMax"),
    ),
    (("throw range", "throw ranges", "throw box"), ("throwRange",)),
    (("throw hurtbox", "throw hurt", "throwable"), ("throwHurt",)),
    (("throw",), ("throwRange", "throwHurt")),
    (("phrase", "win quote", "quote"), ("phrase",)),
)

SF6_STAT_BROAD_TERMS = ("stats", "stat")
SF6_STAT_LEGACY_TERMS = (
    "health",
    "reversal",
    "jump",
    "dash",
    "speed",
    "throw",
    "walk",
    "drive rush",
)


def get_character_input_aliases():
    return deepcopy(CHARACTER_INPUT_ALIASES)
